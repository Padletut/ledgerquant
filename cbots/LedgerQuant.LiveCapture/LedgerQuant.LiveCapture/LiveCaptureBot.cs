using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json;
using cAlgo.API;
using cAlgo.API.Internals;

namespace LedgerQuant.LiveCapture;

[Robot]
public sealed class LiveCaptureBot : Robot
{
    internal const string CaptureVersion = "capture-0.2.0";
    private const int MaximumBatchRecords = 250;
    private const int MaximumBatchBytes = 512_000;

    [Parameter("Feed ID prefix", DefaultValue = "")]
    public string FeedIdPrefix { get; set; } = string.Empty;

    [Parameter("Symbols to capture", DefaultValue = "EURUSD")]
    public Symbol[] SelectedSymbols { get; set; } = Array.Empty<Symbol>();

    [Parameter("Capture all enabled symbols", DefaultValue = true)]
    public bool CaptureAllEnabledSymbols { get; set; } = true;

    [Parameter("Ingest URL", DefaultValue = "http://127.0.0.1:18080/v1/capture/batches")]
    public string IngestUrl { get; set; } = string.Empty;

    [Parameter("Collector token", DefaultValue = "", IsValueVisibleInTitle = false)]
    public string CollectorToken { get; set; } = string.Empty;

    [Parameter("Collect ticks", DefaultValue = false)]
    public bool CollectTicks { get; set; }

    [Parameter("Maximum journal MiB", DefaultValue = 8192, MinValue = 1)]
    public int MaximumJournalMiB { get; set; }

    private readonly List<CaptureFeed> _feeds = new();
    private Uri? _endpoint;
    private int _nextFeedIndex;
    private bool _inFlight;
    private bool _stopping;
    private DateTimeOffset _lastTransportError;
    private DateTimeOffset _retryAfter;

    protected override void OnStart()
    {
        Print("CAPTURE_BOOT version={0}", CaptureVersion);
        try
        {
            if (CollectorToken.Length < 32)
                throw new ArgumentException("Collector token is missing or too short");
            if (!Uri.TryCreate(IngestUrl, UriKind.Absolute, out _endpoint) ||
                (_endpoint.Scheme != Uri.UriSchemeHttps &&
                 !(_endpoint.Scheme == Uri.UriSchemeHttp &&
                   (_endpoint.Host == "127.0.0.1" || _endpoint.Host == "localhost"))))
                throw new ArgumentException("Ingest URL must use HTTPS or loopback HTTP");
            if (MaximumJournalMiB < 1)
                throw new ArgumentException("Maximum journal MiB must be positive");

            var names = CaptureAllEnabledSymbols
                ? Symbols.Enabled.ToArray()
                : (SelectedSymbols ?? Array.Empty<Symbol>())
                    .Select(symbol => symbol?.Name ?? string.Empty).ToArray();
            if (names.Length == 0 || names.Any(string.IsNullOrWhiteSpace))
                throw new ArgumentException("Select at least one capture symbol");
            if (names.Distinct(StringComparer.OrdinalIgnoreCase).Count() != names.Length)
                throw new ArgumentException("Capture symbols contain duplicates");

            var broker = Account.BrokerName;
            var environment = Account.IsLive ? "live" : "demo";
            var accountId = Account.Number.ToString(CultureInfo.InvariantCulture);
            var feedIds = new HashSet<string>(StringComparer.Ordinal);
            foreach (var name in names.OrderBy(name => name, StringComparer.Ordinal))
            {
                if (!Symbols.Exists(name))
                    throw new ArgumentException("Capture symbol is unavailable: " + name);
                var symbol = Symbols.GetSymbol(name) ??
                    throw new ArgumentException("Capture symbol could not be loaded: " + name);
                var feedId = CaptureFeedId.Create(FeedIdPrefix, symbol.Name);
                if (!feedIds.Add(feedId))
                    throw new ArgumentException("Capture symbols derive the same Feed ID: " + feedId);
                _feeds.Add(new CaptureFeed(symbol, feedId, broker, environment, accountId,
                    (long)MaximumJournalMiB * 1024 * 1024, OnFeedFailure));
            }

            foreach (var feed in _feeds)
            {
                feed.Start(MarketData, CollectTicks);
                if (_stopping)
                    return;
            }
            Timer.Start(1);
            Print("CAPTURE_STARTED broker={0} environment={1} account={2} symbols={3} ticks={4} pending_bytes={5}",
                broker, environment, accountId, _feeds.Count, CollectTicks, PendingBytesDescription());
        }
        catch (Exception error)
        {
            Print("CAPTURE_START_FAILED type={0} message={1}", error.GetType().Name, error.Message);
            Stop();
        }
    }

    protected override void OnTimer()
    {
        if (_inFlight || _stopping || _endpoint is null || DateTimeOffset.UtcNow < _retryAfter)
            return;

        for (var offset = 0; offset < _feeds.Count; offset++)
        {
            var index = (_nextFeedIndex + offset) % _feeds.Count;
            var feed = _feeds[index];
            JournalBatch batch;
            try
            {
                batch = feed.ReadBatch(MaximumBatchRecords, MaximumBatchBytes);
            }
            catch (Exception error)
            {
                OnFeedFailure(feed, "CAPTURE_JOURNAL_READ_FAILED", error);
                return;
            }
            if (batch.Records.Count == 0)
                continue;

            _nextFeedIndex = (index + 1) % _feeds.Count;
            SendBatch(feed, batch);
            return;
        }
    }

    private void SendBatch(CaptureFeed feed, JournalBatch batch)
    {
        var sentAt = JsonSerializer.Serialize(DateTimeOffset.UtcNow);
        var body = "{\"protocol_version\":1,\"sent_at\":" + sentAt +
                   ",\"observations\":[" + string.Join(",", batch.Records) + "]}";
        var request = new HttpRequest(_endpoint!)
        {
            Method = cAlgo.API.HttpMethod.Post,
            Body = body,
            Timeout = TimeSpan.FromSeconds(5),
        };
        request.Headers.Add("Authorization", "Bearer " + CollectorToken);
        request.Headers.Add("Content-Type", "application/json");
        _inFlight = true;
        try
        {
            Http.SendAsync(request, response =>
                BeginInvokeOnMainThread(() => HandleResponse(response, feed, batch)));
        }
        catch (Exception error)
        {
            _inFlight = false;
            LogTransportFailure(feed, error.GetType().Name);
        }
    }

    private void HandleResponse(HttpResponse response, CaptureFeed feed, JournalBatch batch)
    {
        if (_stopping)
            return;
        _inFlight = false;
        if (!response.IsSuccessful)
        {
            if (response.StatusCode is 401 or 403 or 409 or 413 or 422)
            {
                OnFeedFailure(feed, "CAPTURE_REJECTED status=" + response.StatusCode, null);
                return;
            }
            LogTransportFailure(feed,
                "HTTP_" + response.StatusCode.ToString(CultureInfo.InvariantCulture));
            return;
        }

        try
        {
            using var receipt = JsonDocument.Parse(response.Body);
            if (!receipt.RootElement.TryGetProperty("committed", out var committed) ||
                committed.GetInt32() != batch.Records.Count)
                throw new InvalidOperationException("ingest acknowledgement count does not match the batch");
            feed.Acknowledge(batch.EndOffset);
        }
        catch (Exception error)
        {
            OnFeedFailure(feed, "CAPTURE_ACK_FAILED", error);
            return;
        }
        OnTimer();
    }

    private void LogTransportFailure(CaptureFeed feed, string reason)
    {
        var now = DateTimeOffset.UtcNow;
        _retryAfter = now + TimeSpan.FromSeconds(5);
        if (now - _lastTransportError < TimeSpan.FromMinutes(1))
            return;
        _lastTransportError = now;
        Print("CAPTURE_TRANSPORT_RETRY feed={0} reason={1} pending_bytes={2}",
            feed.FeedId, reason, PendingBytesDescription());
    }

    private void OnFeedFailure(CaptureFeed feed, string reason, Exception? error)
    {
        if (_stopping)
            return;
        _stopping = true;
        Print("{0} feed={1} symbol={2} type={3} message={4}; local journals retained",
            reason, feed.FeedId, feed.SymbolName,
            error?.GetType().Name ?? "none", error?.Message ?? "none");
        Stop();
    }

    private string PendingBytesDescription()
    {
        try
        {
            return _feeds.Sum(feed => feed.PendingBytes).ToString(CultureInfo.InvariantCulture);
        }
        catch (Exception error)
        {
            return "unavailable:" + error.GetType().Name;
        }
    }

    protected override void OnStop()
    {
        _stopping = true;
        Print("CAPTURE_STOPPED account={0} symbols={1} pending_bytes={2}",
            Account.Number, _feeds.Count, PendingBytesDescription());
        foreach (var feed in _feeds)
            feed.Dispose();
        _feeds.Clear();
    }
}
