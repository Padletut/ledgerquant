using LedgerQuant.MarketData;

var coverage = new TickCoverage();
coverage.Add(new DateTime(2020, 12, 24, 23, 59, 0, DateTimeKind.Utc), 1.10, 1.11);
coverage.Add(new DateTime(2020, 12, 28, 0, 1, 0, DateTimeKind.Utc), 1.10, 1.11);
coverage.Add(new DateTime(2020, 12, 28, 0, 1, 0, DateTimeKind.Utc), 1.12, 1.11);
coverage.Add(new DateTime(2020, 12, 28, 0, 2, 0, DateTimeKind.Utc), double.NaN, 1.11);

var days = coverage.Days.ToArray();
Assert(days.Length == 2, "only observed UTC dates are reported");
Assert(days[0].DateUtc == new DateTime(2020, 12, 24), "first date");
Assert(days[0].Count == 1 && days[0].InvalidQuotes == 0, "first date counts");
Assert(days[1].DateUtc == new DateTime(2020, 12, 28), "second date");
Assert(days[1].Count == 3 && days[1].InvalidQuotes == 2, "second date counts");
Assert(coverage.Count == 4 && coverage.InvalidQuotes == 2, "global counts");
Assert(coverage.DuplicateTimestamps == 1, "equal timestamps remain distinct ticks");
Assert(coverage.LargestGap > TimeSpan.FromDays(3), "gap retained for review");

Console.WriteLine("market-data tick coverage contract passed");

static void Assert(bool condition, string description)
{
    if (!condition)
        throw new Exception(description);
}
