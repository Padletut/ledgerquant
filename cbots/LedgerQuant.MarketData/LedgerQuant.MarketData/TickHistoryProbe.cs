using System;
using System.Globalization;
using cAlgo.API;

namespace LedgerQuant.MarketData;

[Robot(TimeZone = TimeZones.UTC, AccessRights = AccessRights.None)]
public sealed class TickHistoryProbe : Robot
{
    [Parameter("Target date UTC", DefaultValue = "2020-01-01")]
    public string TargetDateUtc { get; set; } = "2020-01-01";

    [Parameter("Load older history", DefaultValue = false)]
    public bool LoadOlderHistory { get; set; }

    [Parameter("Max history batches", DefaultValue = 20, MinValue = 1, MaxValue = 1000)]
    public int MaxHistoryBatches { get; set; }

    [Parameter("Max cached ticks", DefaultValue = 500000, MinValue = 1000)]
    public int MaxCachedTicks { get; set; }

    private readonly TickCoverage _observed = new();
    private Ticks? _ticks;
    private DateTime _target;
    private DateTime? _reportedServerFirst;
    private DateTime? _retrievedFirst;
    private int _historyBatches;
    private long _loadedTicks;
    private string _historyStatus = "NOT_REQUESTED";

    protected override void OnStart()
    {
        if (!DateTime.TryParseExact(TargetDateUtc, "yyyy-MM-dd", CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out _target))
        {
            _historyStatus = "INVALID_TARGET_DATE";
            Print("TICK_PROBE_ERROR invalid_target_date expected=yyyy-MM-dd");
            Stop();
            return;
        }

        _ticks = MarketData.GetTicks(SymbolName);
        _reportedServerFirst = _ticks.GetServerFirstTime();
        Print("TICK_PROBE_START symbol={0} account={1} target_utc={2:O} server_first_reported_utc={3:O} load_older_history={4}",
            SymbolName, Account.Number, _target, _reportedServerFirst, LoadOlderHistory);

        if (LoadOlderHistory)
        {
            _historyStatus = "IN_PROGRESS";
            Timer.Start(1);
        }
    }

    protected override void OnTick()
    {
        if (_ticks is null)
            return;

        _observed.Add(_ticks.LastTick);
    }

    protected override void OnTimer()
    {
        if (_ticks is null)
            return;

        if (_ticks.Count > 0)
        {
            _retrievedFirst = _ticks[0].Time;
            if (_retrievedFirst <= _target)
            {
                _historyStatus = "TARGET_RETRIEVED";
                Stop();
                return;
            }
        }

        if (_historyBatches >= MaxHistoryBatches || _ticks.Count >= MaxCachedTicks)
        {
            _historyStatus = "RESOURCE_LIMIT";
            Stop();
            return;
        }

        try
        {
            var added = _ticks.LoadMoreHistory();
            _historyBatches++;
            _loadedTicks += added;
            if (_ticks.Count > 0)
                _retrievedFirst = _ticks[0].Time;

            Print("TICK_PROBE_LOAD batch={0} added={1} cached={2} oldest_utc={3:O}",
                _historyBatches, added, _ticks.Count, _retrievedFirst);

            if (_retrievedFirst <= _target)
                _historyStatus = "TARGET_RETRIEVED";
            else if (added == 0)
                _historyStatus = "NO_MORE_HISTORY_RETURNED";
            else if (_ticks.Count >= MaxCachedTicks)
                _historyStatus = "RESOURCE_LIMIT";
            else
                return;
        }
        catch (Exception error)
        {
            _historyStatus = "LOAD_ERROR";
            Print("TICK_PROBE_LOAD_ERROR type={0} message={1}", error.GetType().Name, error.Message);
        }

        Stop();
    }

    protected override void OnStop()
    {
        Print("TICK_PROBE_RESULT symbol={0} account={1} target_utc={2:O} server_first_reported_utc={3:O} history_status={4} history_batches={5} history_ticks_added={6} earliest_retrieved_utc={7:O} observed_ticks={8} observed_first_utc={9:O} observed_last_utc={10:O} invalid_quotes={11} duplicate_timestamps={12} reversed_timestamps={13} largest_observed_gap_seconds={14}",
            SymbolName, Account.Number, _target, _reportedServerFirst, _historyStatus,
            _historyBatches, _loadedTicks, _retrievedFirst, _observed.Count,
            _observed.FirstTime, _observed.LastTime, _observed.InvalidQuotes,
            _observed.DuplicateTimestamps, _observed.ReversedTimestamps,
            _observed.LargestGap.TotalSeconds.ToString(CultureInfo.InvariantCulture));
    }
}
