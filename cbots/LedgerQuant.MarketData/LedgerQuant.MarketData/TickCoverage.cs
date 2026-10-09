using System;
using System.Collections.Generic;

namespace LedgerQuant.MarketData;

internal sealed class TickCoverage
{
    private readonly SortedDictionary<DateTime, TickDayCoverage> _days = new();

    public long Count { get; private set; }
    public long InvalidQuotes { get; private set; }
    public long DuplicateTimestamps { get; private set; }
    public long ReversedTimestamps { get; private set; }
    public DateTime? FirstTime { get; private set; }
    public DateTime? LastTime { get; private set; }
    public TimeSpan LargestGap { get; private set; }
    public IEnumerable<TickDayCoverage> Days => _days.Values;

    public void Add(DateTime timeUtc, double bid, double ask)
    {
        if (LastTime.HasValue)
        {
            var gap = timeUtc - LastTime.Value;
            if (gap < TimeSpan.Zero)
                ReversedTimestamps++;
            else if (gap == TimeSpan.Zero)
                DuplicateTimestamps++;
            else if (gap > LargestGap)
                LargestGap = gap;
        }

        var invalidQuote = !double.IsFinite(bid) || !double.IsFinite(ask) ||
            bid <= 0 || ask <= 0 || ask < bid;
        if (invalidQuote)
            InvalidQuotes++;

        var dateUtc = timeUtc.Date;
        if (!_days.TryGetValue(dateUtc, out var day))
        {
            day = new TickDayCoverage(dateUtc);
            _days.Add(dateUtc, day);
        }

        day.Add(timeUtc, invalidQuote);
        FirstTime ??= timeUtc;
        LastTime = timeUtc;
        Count++;
    }
}

internal sealed class TickDayCoverage
{
    public TickDayCoverage(DateTime dateUtc) => DateUtc = dateUtc;

    public DateTime DateUtc { get; }
    public long Count { get; private set; }
    public long InvalidQuotes { get; private set; }
    public DateTime? FirstTime { get; private set; }
    public DateTime? LastTime { get; private set; }

    public void Add(DateTime timeUtc, bool invalidQuote)
    {
        FirstTime ??= timeUtc;
        LastTime = timeUtc;
        Count++;
        if (invalidQuote)
            InvalidQuotes++;
    }
}
