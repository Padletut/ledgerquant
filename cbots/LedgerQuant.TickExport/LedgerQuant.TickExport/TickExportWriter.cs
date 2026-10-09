using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace LedgerQuant.TickExport;

internal sealed record TickExportSource(
    string RunId,
    string BrokerName,
    string BrokerNameBasis,
    int AccountNumber,
    bool IsLive,
    string Symbol,
    DateTime StartUtc,
    DateTime EndExclusiveUtc,
    string CliImageDigest,
    string ExporterVersion);

internal sealed class TickExportWriter : IDisposable
{
    private static readonly Regex SafeRunId = new("^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$",
        RegexOptions.Compiled | RegexOptions.CultureInvariant);

    private readonly TickExportSource _source;
    private readonly long _maxRows;
    private readonly DateTime _startedAtUtc;
    private readonly string _partialDataPath;
    private readonly string _dataPath;
    private readonly string _manifestPath;
    private readonly StreamWriter _writer;
    private readonly FileStream _stream;
    private bool _closed;
    private DateTime? _firstTimeUtc;
    private DateTime? _lastTimeUtc;

    public long RowCount { get; private set; }
    public long DuplicateTimestamps { get; private set; }
    public long ZeroSpreadRows { get; private set; }
    public bool IsComplete { get; private set; }
    public string DataPath => _dataPath;
    public string ManifestPath => _manifestPath;

    public TickExportWriter(string outputDirectory, TickExportSource source, long maxRows,
        DateTime startedAtUtc)
    {
        if (string.IsNullOrWhiteSpace(outputDirectory) || !Path.IsPathFullyQualified(outputDirectory) ||
            !Directory.Exists(outputDirectory))
            throw new ArgumentException("Output directory must be an existing absolute path.",
                nameof(outputDirectory));
        if (source is null)
            throw new ArgumentNullException(nameof(source));
        if (!SafeRunId.IsMatch(source.RunId))
            throw new ArgumentException("Run ID has unsafe characters.", nameof(source));
        if (string.IsNullOrWhiteSpace(source.BrokerName) ||
            source.BrokerNameBasis is not ("account_api_verified" or "cli_accounts_asserted") ||
            source.AccountNumber <= 0 ||
            string.IsNullOrWhiteSpace(source.Symbol))
            throw new ArgumentException("Broker, account or symbol identity is missing.", nameof(source));
        if (string.IsNullOrWhiteSpace(source.CliImageDigest) ||
            string.IsNullOrWhiteSpace(source.ExporterVersion))
            throw new ArgumentException("CLI image or exporter version is missing.", nameof(source));
        if (source.StartUtc.Kind != DateTimeKind.Utc ||
            source.EndExclusiveUtc.Kind != DateTimeKind.Utc ||
            source.StartUtc >= source.EndExclusiveUtc ||
            source.EndExclusiveUtc - source.StartUtc > TimeSpan.FromDays(7))
            throw new ArgumentException("UTC interval is invalid or exceeds seven days.", nameof(source));
        if (maxRows <= 0 || maxRows > 1_000_000)
            throw new ArgumentOutOfRangeException(nameof(maxRows));
        if (startedAtUtc.Kind != DateTimeKind.Utc)
            throw new ArgumentException("Extraction start must be UTC.", nameof(startedAtUtc));

        _source = source;
        _maxRows = maxRows;
        _startedAtUtc = startedAtUtc;
        _partialDataPath = Path.Combine(outputDirectory, source.RunId + ".ticks.csv.part");
        _dataPath = Path.Combine(outputDirectory, source.RunId + ".ticks.csv");
        _manifestPath = Path.Combine(outputDirectory, source.RunId + ".manifest.json");
        if (File.Exists(_partialDataPath) || File.Exists(_dataPath) ||
            File.Exists(_manifestPath) || File.Exists(_manifestPath + ".part"))
            throw new IOException("Run ID already has an output artifact; refusing to overwrite it.");

        _stream = new FileStream(_partialDataPath, FileMode.CreateNew, FileAccess.Write,
            FileShare.None, 65536, FileOptions.SequentialScan);
        _writer = new StreamWriter(_stream, new UTF8Encoding(false), 65536)
        {
            NewLine = "\n"
        };
        _writer.WriteLine("ordinal,event_time_utc,bid,ask");
    }

    public void Add(DateTime eventTimeUtc, double bid, double ask)
    {
        if (_closed)
            throw new InvalidOperationException("Export is already closed.");
        if (eventTimeUtc.Kind != DateTimeKind.Utc || eventTimeUtc < _source.StartUtc ||
            eventTimeUtc >= _source.EndExclusiveUtc)
            throw new InvalidDataException("Tick is outside the declared UTC interval.");
        if (!double.IsFinite(bid) || !double.IsFinite(ask) || bid <= 0 || ask <= 0 || ask < bid)
            throw new InvalidDataException("Tick has an invalid bid/ask quote.");
        if (_lastTimeUtc.HasValue && eventTimeUtc < _lastTimeUtc.Value)
            throw new InvalidDataException("Tick timestamps run backwards.");
        if (RowCount >= _maxRows)
            throw new IOException("Tick export reached its configured row limit.");

        if (_lastTimeUtc == eventTimeUtc)
            DuplicateTimestamps++;
        if (ask == bid)
            ZeroSpreadRows++;
        _firstTimeUtc ??= eventTimeUtc;
        _lastTimeUtc = eventTimeUtc;
        RowCount++;
        _writer.Write(RowCount.ToString(CultureInfo.InvariantCulture));
        _writer.Write(',');
        _writer.Write(eventTimeUtc.ToString("O", CultureInfo.InvariantCulture));
        _writer.Write(',');
        _writer.Write(bid.ToString("R", CultureInfo.InvariantCulture));
        _writer.Write(',');
        _writer.WriteLine(ask.ToString("R", CultureInfo.InvariantCulture));
    }

    public void Complete(DateTime completedAtUtc)
    {
        if (_closed)
            throw new InvalidOperationException("Export is already closed.");
        if (completedAtUtc.Kind != DateTimeKind.Utc || completedAtUtc < _startedAtUtc)
            throw new ArgumentException("Extraction completion must be UTC and after start.",
                nameof(completedAtUtc));

        _writer.Flush();
        _stream.Flush(flushToDisk: true);
        _writer.Dispose();
        _closed = true;

        string hash;
        using (var read = File.OpenRead(_partialDataPath))
        using (var sha = SHA256.Create())
            hash = Convert.ToHexString(sha.ComputeHash(read)).ToLowerInvariant();
        var bytes = new FileInfo(_partialDataPath).Length;
        File.Move(_partialDataPath, _dataPath);

        var manifest = new
        {
            schema_version = 1,
            run_id = _source.RunId,
            source_type = "broker_historical_tick_backfill",
            broker_name = _source.BrokerName,
            broker_name_basis = _source.BrokerNameBasis,
            account_number = _source.AccountNumber,
            account_environment = _source.IsLive ? "live" : "demo",
            server_identity = (string?)null,
            broker_symbol = _source.Symbol,
            data_mode = "ctrader_cli_server_ticks",
            cli_image_digest = _source.CliImageDigest,
            exporter_version = _source.ExporterVersion,
            requested_start_utc = Utc(_source.StartUtc),
            requested_end_exclusive_utc = Utc(_source.EndExclusiveUtc),
            first_event_utc = _firstTimeUtc.HasValue ? Utc(_firstTimeUtc.Value) : null,
            last_event_utc = _lastTimeUtc.HasValue ? Utc(_lastTimeUtc.Value) : null,
            row_count = RowCount,
            duplicate_timestamps = DuplicateTimestamps,
            zero_spread_rows = ZeroSpreadRows,
            data_file = Path.GetFileName(_dataPath),
            data_bytes = bytes,
            data_sha256 = hash,
            extraction_started_at_utc = Utc(_startedAtUtc),
            extraction_completed_at_utc = Utc(completedAtUtc),
            observed_at_utc = (string?)null,
            available_at_utc = (string?)null,
            coverage_status = "UNVERIFIED",
            quote_quality_status = "UNVERIFIED"
        };
        var manifestPart = _manifestPath + ".part";
        using (var output = new FileStream(manifestPart, FileMode.CreateNew, FileAccess.Write,
                   FileShare.None))
        {
            JsonSerializer.Serialize(output, manifest, new JsonSerializerOptions
            {
                WriteIndented = true
            });
            output.Flush(flushToDisk: true);
        }
        File.Move(manifestPart, _manifestPath);
        IsComplete = true;
    }

    public void Dispose()
    {
        if (!_closed)
        {
            _closed = true;
            _writer.Dispose();
        }
    }

    private static string Utc(DateTime value) => value.ToString("O", CultureInfo.InvariantCulture);
}
