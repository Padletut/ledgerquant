using System.Globalization;
using cAlgo.API;

namespace LedgerQuant.TickExport;

[Robot(TimeZone = TimeZones.UTC, AccessRights = AccessRights.FullAccess)]
public sealed class TickExportRobot : Robot
{
    private const string ExporterVersion = "tick-export-0.1.0";

    [Parameter("Start UTC")]
    public string StartUtc { get; set; } = string.Empty;

    [Parameter("End exclusive UTC")]
    public string EndExclusiveUtc { get; set; } = string.Empty;

    [Parameter("Output directory")]
    public string OutputDirectory { get; set; } = string.Empty;

    [Parameter("Run ID")]
    public string RunId { get; set; } = string.Empty;

    [Parameter("Expected account number")]
    public int ExpectedAccountNumber { get; set; }

    [Parameter("Expected broker name")]
    public string ExpectedBrokerName { get; set; } = string.Empty;

    [Parameter("CLI image digest")]
    public string CliImageDigest { get; set; } = string.Empty;

    [Parameter("Maximum rows", DefaultValue = 250000, MinValue = 1, MaxValue = 1000000)]
    public int MaximumRows { get; set; }

    private TickExportWriter? _writer;
    private Ticks? _ticks;
    private DateTime _start;
    private DateTime _end;
    private bool _warmupObserved;
    private string? _failure;

    protected override void OnStart()
    {
        try
        {
            if (!IsBacktesting)
                throw new InvalidOperationException("Historical export requires backtesting mode.");
            if (ExpectedAccountNumber <= 0 || Account.Number != ExpectedAccountNumber)
                throw new InvalidOperationException("The account does not match the expected number.");
            if (string.IsNullOrWhiteSpace(ExpectedBrokerName))
                throw new ArgumentException("Expected broker name is required.");
            var runtimeBrokerName = Account.BrokerName;
            if (!string.IsNullOrWhiteSpace(runtimeBrokerName) &&
                !string.Equals(runtimeBrokerName, ExpectedBrokerName,
                    StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("The account does not match the expected broker.");
            _start = ParseUtc(StartUtc);
            _end = ParseUtc(EndExclusiveUtc);
            var brokerNameBasis = string.IsNullOrWhiteSpace(runtimeBrokerName)
                ? "cli_accounts_asserted" : "account_api_verified";
            var source = new TickExportSource(RunId, ExpectedBrokerName.Trim(), brokerNameBasis,
                Account.Number, Account.IsLive, SymbolName, _start, _end,
                CliImageDigest, ExporterVersion);
            _writer = new TickExportWriter(OutputDirectory, source, MaximumRows, DateTime.UtcNow);
            _ticks = MarketData.GetTicks(SymbolName);
            Print("TICK_EXPORT_START run_id={0} broker={1} account={2} live={3} symbol={4} start_utc={5:O} end_exclusive_utc={6:O} max_rows={7}",
                RunId, ExpectedBrokerName, Account.Number, Account.IsLive, SymbolName,
                _start, _end, MaximumRows);
        }
        catch (Exception error)
        {
            Fail(error);
        }
    }

    protected override void OnTick()
    {
        if (_writer is null || _ticks is null || _failure is not null)
            return;

        try
        {
            var tick = _ticks.LastTick;
            if (tick.Time < _start)
            {
                _warmupObserved = true;
                return;
            }
            if (!_warmupObserved)
                throw new InvalidDataException("No pre-window warm-up tick was observed.");
            if (tick.Time >= _end)
            {
                _writer.Complete(DateTime.UtcNow);
                Print("TICK_EXPORT_COMPLETE run_id={0} rows={1} duplicate_timestamps={2} zero_spread_rows={3} data_file={4} manifest_file={5}",
                    RunId, _writer.RowCount, _writer.DuplicateTimestamps,
                    _writer.ZeroSpreadRows,
                    _writer.DataPath, _writer.ManifestPath);
                Stop();
                return;
            }
            _writer.Add(tick.Time, tick.Bid, tick.Ask);
        }
        catch (Exception error)
        {
            Fail(error);
        }
    }

    protected override void OnStop()
    {
        if (_writer is not null && !_writer.IsComplete)
            Print("TICK_EXPORT_INCOMPLETE run_id={0} reason={1} rows={2}",
                RunId, _failure ?? "NO_END_WITNESS", _writer.RowCount);
        _writer?.Dispose();
    }

    private void Fail(Exception error)
    {
        _failure = error.GetType().Name;
        Print("TICK_EXPORT_FAILED run_id={0} type={1} message={2}",
            RunId, error.GetType().Name, error.Message);
        Stop();
    }

    private static DateTime ParseUtc(string value)
    {
        if (!DateTime.TryParseExact(value, "yyyy-MM-ddTHH:mm:ss'Z'",
                CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal,
                out var parsed))
            throw new ArgumentException("Expected UTC timestamp yyyy-MM-ddTHH:mm:ssZ.");
        return parsed;
    }
}
