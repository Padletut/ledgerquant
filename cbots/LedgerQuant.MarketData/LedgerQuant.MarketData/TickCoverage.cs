using System;
using cAlgo.API;

namespace LedgerQuant.MarketData;

internal sealed class TickCoverage
{
    public long Count { get; private set; }
    public long InvalidQuotes { get; private set; }
    public long DuplicateTimestamps { get; private set; }
    public long ReversedTimestamps { get; private set; }
    public DateTime? FirstTime { get; private set; }
    public DateTime? LastTime { get; private set; }
    public TimeSpan LargestGap { get; private set; }

    public void Add(Tick tick)
    {
        if (LastTime.HasValue)
        {
            var gap = tick.Time - LastTime.Value;
            if (gap < TimeSpan.Zero)
                ReversedTimestamps++;
            else if (gap == TimeSpan.Zero)
                DuplicateTimestamps++;
            else if (gap > LargestGap)
                LargestGap = gap;
        }

        if (tick.Bid <= 0 || tick.Ask <= 0 || tick.Ask < tick.Bid)
            InvalidQuotes++;

        FirstTime ??= tick.Time;
        LastTime = tick.Time;
        Count++;
    }
}
