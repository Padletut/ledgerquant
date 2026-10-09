using System;
using System.Text.Json;
using cAlgo.API;
using cAlgo.API.Internals;

namespace LedgerQuant.LiveCapture;

internal sealed class CaptureFeed : IDisposable
{
    private readonly Symbol _symbol;
    private readonly string _broker;
    private readonly string _environment;
    private readonly string _accountId;
    private readonly Action<CaptureFeed, string, Exception?> _onFailure;
    private readonly CaptureJournal _journal;
    private readonly Guid _sessionId = Guid.NewGuid();
    private SymbolSentiment? _sentiment;
    private Ticks? _ticks;
    private long _sequence;
    private bool _disposed;

    public CaptureFeed(Symbol symbol, string feedId, string broker, string environment,
        string accountId, long maximumJournalBytes,
        Action<CaptureFeed, string, Exception?> onFailure)
    {
        _symbol = symbol;
        FeedId = feedId;
        _broker = broker;
        _environment = environment;
        _accountId = accountId;
        _onFailure = onFailure;
        var sourceIdentity = JsonSerializer.Serialize(new
        {
            source = "ctrader",
            broker,
            environment,
            account_id = accountId,
            symbol = symbol.Name,
        });
        _journal = new CaptureJournal(feedId, sourceIdentity, maximumJournalBytes);
    }

    public string FeedId { get; }
    public string SymbolName => _symbol.Name;
    public long PendingBytes => _journal.PendingBytes;

    public void Start(MarketData marketData, bool collectTicks)
    {
        if (collectTicks)
        {
            _ticks = marketData.GetTicks(SymbolName);
            _ticks.Tick += OnTicksTick;
        }
        _sentiment = _symbol.Sentiment ??
            throw new InvalidOperationException("symbol sentiment API is unavailable");
        _sentiment.Updated += OnSentimentUpdated;
        RecordSentiment(_sentiment, "startup");
    }

    public JournalBatch ReadBatch(int maximumRecords, int maximumBytes) =>
        _journal.ReadBatch(maximumRecords, maximumBytes);

    public void Acknowledge(long endOffset) => _journal.Acknowledge(endOffset);

    private void OnTicksTick(TicksTickEventArgs args)
    {
        if (_disposed)
            return;
        if (args.Ticks.Count == 0)
        {
            _onFailure(this, "CAPTURE_TICK_SOURCE_EMPTY", null);
            return;
        }
        try
        {
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
        catch (Exception error)
        {
            _onFailure(this, "CAPTURE_JOURNAL_FAILED", error);
        }
    }

    private void OnSentimentUpdated(SymbolSentimentUpdatedEventArgs args)
    {
        if (_disposed || args.SymbolName != SymbolName)
            return;
        try
        {
            RecordSentiment(args.Sentiment, "update");
        }
        catch (Exception error)
        {
            _onFailure(this, "CAPTURE_JOURNAL_FAILED", error);
        }
    }

    private void RecordSentiment(SymbolSentiment sentiment, string trigger) =>
        Record(new CaptureObservation
        {
            MessageId = Guid.NewGuid(),
            ObservedAt = DateTimeOffset.UtcNow,
            BuyPercentage = sentiment.BuyPercentage,
            SellPercentage = sentiment.SellPercentage,
            SentimentTrigger = trigger,
            Kind = "sentiment",
        });

    private void Record(CaptureObservation observation)
    {
        var complete = new CaptureObservation
        {
            MessageId = observation.MessageId,
            FeedId = FeedId,
            SessionId = _sessionId,
            Sequence = ++_sequence,
            Broker = _broker,
            Environment = _environment,
            AccountId = _accountId,
            Symbol = SymbolName,
            Kind = observation.Kind,
            EventAt = observation.EventAt,
            ObservedAt = observation.ObservedAt,
            Bid = observation.Bid,
            Ask = observation.Ask,
            BuyPercentage = observation.BuyPercentage,
            SellPercentage = observation.SellPercentage,
            SentimentTrigger = observation.SentimentTrigger,
            CbotVersion = LiveCaptureBot.CaptureVersion,
        };
        _journal.Append(JsonSerializer.Serialize(complete));
    }

    public void Dispose()
    {
        if (_disposed)
            return;
        _disposed = true;
        if (_sentiment is not null)
            _sentiment.Updated -= OnSentimentUpdated;
        if (_ticks is not null)
            _ticks.Tick -= OnTicksTick;
        _journal.Dispose();
    }
}
