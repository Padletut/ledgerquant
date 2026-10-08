using System;
using System.Globalization;
using System.Linq;
using System.Text.Json;
using cAlgo.API;

namespace LedgerQuant.LiveCapture;

[Robot(TimeZone = TimeZones.UTC, AccessRights = AccessRights.None)]
public sealed class LiveCaptureBot : Robot
{
    private const string CaptureVersion = "capture-0.1.0";
    private const int MaximumBatchRecords = 250;
    private const int MaximumBatchBytes = 512_000;

    [Parameter("Feed ID", DefaultValue = "")]
    public string FeedId { get; set; } = string.Empty;

    [Parameter("Ingest URL", DefaultValue = "http://127.0.0.1:18080/v1/capture/batches")]
    public string IngestUrl { get; set; } = string.Empty;

    [Parameter("Collector token", DefaultValue = "")]
    public string CollectorToken { get; set; } = string.Empty;

    [Parameter("Collect ticks", DefaultValue = false)]
    public bool CollectTicks { get; set; }

    [Parameter("Maximum journal MiB", DefaultValue = 8192, MinValue = 1)]
    public int MaximumJournalMiB { get; set; }

    private CaptureJournal? _journal;
    private Ticks? _ticks;
    private SymbolSentiment? _sentiment;
    private Uri? _endpoint;
    private Guid _sessionId;
    private long _sequence;
    private bool _inFlight;
    private bool _stopping;
    private DateTimeOffset _lastTransportError;

    protected override void OnStart()
    {
        try
        {
            if (FeedId.Length is < 1 or > 100 ||
                FeedId.Any(character =>
                    !(character is >= 'A' and <= 'Z' or >= 'a' and <= 'z' or >= '0' and <= '9' or '_' or '-')))
                throw new ArgumentException("Feed ID must contain only ASCII letters, digits, _ or -");
            if (CollectorToken.Length < 32)
                throw new ArgumentException("Collector token is missing or too short");
            if (!Uri.TryCreate(IngestUrl, UriKind.Absolute, out _endpoint) ||
                (_endpoint.Scheme != Uri.UriSchemeHttps &&
                 !(_endpoint.Scheme == Uri.UriSchemeHttp &&
                   (_endpoint.Host == "127.0.0.1" || _endpoint.Host == "localhost"))))
                throw new ArgumentException("Ingest URL must use HTTPS or loopback HTTP");

            var sourceIdentity = JsonSerializer.Serialize(new
            {
                source = "ctrader",
                broker = Account.BrokerName,
                environment = Account.IsLive ? "live" : "demo",
                account_id = Account.Number.ToString(CultureInfo.InvariantCulture),
                symbol = SymbolName,
            });
            _journal = new CaptureJournal(FeedId, sourceIdentity,
                (long)MaximumJournalMiB * 1024 * 1024);
            _sessionId = Guid.NewGuid();
            if (CollectTicks)
            {
                _ticks = MarketData.GetTicks(SymbolName);
                _ticks.Tick += OnTicksTick;
            }

            _sentiment = Symbol.Sentiment;
            _sentiment.Updated += OnSentimentUpdated;
            RecordSentiment(_sentiment, "startup");
            if (_stopping)
                return;
            Timer.Start(1);
            Print("CAPTURE_STARTED feed={0} broker={1} environment={2} account={3} symbol={4} ticks={5} pending_bytes={6}",
                FeedId, Account.BrokerName, Account.IsLive ? "live" : "demo",
                Account.Number, SymbolName, CollectTicks, _journal.PendingBytes);
        }
        catch (Exception error)
        {
            Print("CAPTURE_START_FAILED type={0} message={1}", error.GetType().Name, error.Message);
            Stop();
        }
    }

    private void OnTicksTick(TicksTickEventArgs args)
    {
        if (args.Ticks.Count == 0)
        {
            _stopping = true;
            Print("CAPTURE_TICK_SOURCE_EMPTY; local journal retained");
            Stop();
            return;
        }
        var tick = args.Ticks.LastTick;
        Record(new CaptureObservation
        {
            MessageId = Guid.NewGuid(),
            EventAt = new DateTimeOffset(DateTime.SpecifyKind(tick.Time, DateTimeKind.Utc)),
            ObservedAt = DateTimeOffset.UtcNow,
            Bid = tick.Bid,
            Ask = tick.Ask,
            Kind = "tick",
        });
    }

    private void OnSentimentUpdated(SymbolSentimentUpdatedEventArgs args)
    {
        if (args.SymbolName == SymbolName)
            RecordSentiment(args.Sentiment, "update");
    }

    private void RecordSentiment(SymbolSentiment sentiment, string trigger)
    {
        Record(new CaptureObservation
        {
            MessageId = Guid.NewGuid(),
            ObservedAt = DateTimeOffset.UtcNow,
            BuyPercentage = sentiment.BuyPercentage,
            SellPercentage = sentiment.SellPercentage,
            SentimentTrigger = trigger,
            Kind = "sentiment",
        });
    }

    private void Record(CaptureObservation observation)
    {
        if (_stopping || _journal is null)
            return;
        try
        {
            var complete = new CaptureObservation
            {
                MessageId = observation.MessageId,
                FeedId = FeedId,
                SessionId = _sessionId,
                Sequence = ++_sequence,
                Broker = Account.BrokerName,
                Environment = Account.IsLive ? "live" : "demo",
                AccountId = Account.Number.ToString(CultureInfo.InvariantCulture),
                Symbol = SymbolName,
                Kind = observation.Kind,
                EventAt = observation.EventAt,
                ObservedAt = observation.ObservedAt,
                Bid = observation.Bid,
                Ask = observation.Ask,
                BuyPercentage = observation.BuyPercentage,
                SellPercentage = observation.SellPercentage,
                SentimentTrigger = observation.SentimentTrigger,
                CbotVersion = CaptureVersion,
            };
            _journal.Append(JsonSerializer.Serialize(complete));
        }
        catch (Exception error)
        {
            _stopping = true;
            Print("CAPTURE_JOURNAL_FAILED type={0} message={1}", error.GetType().Name, error.Message);
            Stop();
        }
    }

    protected override void OnTimer()
    {
        if (_inFlight || _stopping || _journal is null || _endpoint is null)
            return;
        JournalBatch batch;
        try
        {
            batch = _journal.ReadBatch(MaximumBatchRecords, MaximumBatchBytes);
        }
        catch (Exception error)
        {
            _stopping = true;
            Print("CAPTURE_JOURNAL_READ_FAILED type={0} message={1}", error.GetType().Name, error.Message);
            Stop();
            return;
        }
        if (batch.Records.Count == 0)
            return;

        var sentAt = JsonSerializer.Serialize(DateTimeOffset.UtcNow);
        var body = "{\"protocol_version\":1,\"sent_at\":" + sentAt +
                   ",\"observations\":[" + string.Join(",", batch.Records) + "]}";
        var request = new HttpRequest(_endpoint)
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
                BeginInvokeOnMainThread(() => HandleResponse(response, batch)));
        }
        catch (Exception error)
        {
            _inFlight = false;
            LogTransportFailure(error.GetType().Name);
        }
    }

    private void HandleResponse(HttpResponse response, JournalBatch batch)
    {
        if (_stopping || _journal is null)
            return;
        _inFlight = false;
        if (!response.IsSuccessful)
        {
            if (response.StatusCode is 401 or 403 or 409 or 413 or 422)
            {
                _stopping = true;
                Print("CAPTURE_REJECTED status={0}; local journal retained", response.StatusCode);
                Stop();
                return;
            }
            LogTransportFailure("HTTP_" + response.StatusCode.ToString(CultureInfo.InvariantCulture));
            return;
        }

        try
        {
            using var receipt = JsonDocument.Parse(response.Body);
            if (!receipt.RootElement.TryGetProperty("committed", out var committed) ||
                committed.GetInt32() != batch.Records.Count)
                throw new InvalidOperationException("ingest acknowledgement count does not match the batch");
            _journal.Acknowledge(batch.EndOffset);
        }
        catch (Exception error)
        {
            _stopping = true;
            Print("CAPTURE_ACK_FAILED type={0} message={1}; local journal retained",
                error.GetType().Name, error.Message);
            Stop();
        }
    }

    private void LogTransportFailure(string reason)
    {
        var now = DateTimeOffset.UtcNow;
        if (now - _lastTransportError < TimeSpan.FromMinutes(1))
            return;
        _lastTransportError = now;
        Print("CAPTURE_TRANSPORT_RETRY reason={0} pending_bytes={1}",
            reason, _journal?.PendingBytes);
    }

    protected override void OnStop()
    {
        _stopping = true;
        if (_sentiment is not null)
            _sentiment.Updated -= OnSentimentUpdated;
        if (_ticks is not null)
            _ticks.Tick -= OnTicksTick;
        Print("CAPTURE_STOPPED feed={0} pending_bytes={1}", FeedId, _journal?.PendingBytes);
        _journal?.Dispose();
    }
}
