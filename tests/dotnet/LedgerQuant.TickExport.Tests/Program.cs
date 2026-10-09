using System.Security.Cryptography;
using System.Text.Json;
using LedgerQuant.TickExport;

var directory = Path.Combine(Path.GetTempPath(), "ledgerquant-tick-export-" + Guid.NewGuid());
Directory.CreateDirectory(directory);
var source = new TickExportSource("run_20200102", "IC Markets EU Ltd",
    "cli_accounts_asserted", 12345, true,
    "EURUSD", new DateTime(2020, 1, 2, 0, 0, 0, DateTimeKind.Utc),
    new DateTime(2020, 1, 3, 0, 0, 0, DateTimeKind.Utc), "sha256:test-image", "test-exporter");

try
{
    var first = new DateTime(2020, 1, 2, 0, 0, 0, DateTimeKind.Utc).AddMilliseconds(471);
    using (var writer = new TickExportWriter(directory, source, maxRows: 3,
               startedAtUtc: new DateTime(2026, 10, 9, 12, 0, 0, DateTimeKind.Utc)))
    {
        writer.Add(first, 1.102, 1.102);
        writer.Add(first, 1.104, 1.105);
        writer.Add(first.AddMilliseconds(1), 1.106, 1.107);
        writer.Complete(new DateTime(2026, 10, 9, 12, 1, 0, DateTimeKind.Utc));
    }

    var dataPath = Path.Combine(directory, "run_20200102.ticks.csv");
    var manifestPath = Path.Combine(directory, "run_20200102.manifest.json");
    Assert(File.Exists(dataPath) && File.Exists(manifestPath), "data and manifest committed");
    var lines = File.ReadAllLines(dataPath);
    Assert(lines.Length == 4 && lines[0] == "ordinal,event_time_utc,bid,ask", "header and rows");
    Assert(lines[1].StartsWith("1,2020-01-02T00:00:00.4710000Z,"), "first event time");
    Assert(lines[2].StartsWith("2,2020-01-02T00:00:00.4710000Z,"), "equal-time update retained");
    using (var manifest = JsonDocument.Parse(File.ReadAllText(manifestPath)))
    {
        var root = manifest.RootElement;
        Assert(root.GetProperty("row_count").GetInt64() == 3, "row count");
        Assert(root.GetProperty("duplicate_timestamps").GetInt64() == 1, "duplicate timestamp count");
        Assert(root.GetProperty("zero_spread_rows").GetInt64() == 1, "zero-spread observations retained and counted");
        Assert(root.GetProperty("quote_quality_status").GetString() == "UNVERIFIED",
            "quote quality is not certified by export success");
        Assert(root.GetProperty("account_number").GetInt32() == 12345, "account identity");
        Assert(root.GetProperty("account_environment").GetString() == "live", "environment identity");
        Assert(root.GetProperty("broker_name_basis").GetString() == "cli_accounts_asserted",
            "broker provenance");
        Assert(root.GetProperty("data_sha256").GetString() ==
               Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(dataPath))).ToLowerInvariant(),
            "content hash");
        Assert(root.GetProperty("available_at_utc").ValueKind == JsonValueKind.Null,
            "historical availability is not invented");
    }

    ExpectFailure(() => new TickExportWriter(directory, source, 3, DateTime.UtcNow),
        "existing run cannot be overwritten");

    var invalidSource = source with { RunId = "invalid_quote" };
    using (var writer = new TickExportWriter(directory, invalidSource, 3, DateTime.UtcNow))
    {
        ExpectFailure(() => writer.Add(first, 1.2, 1.1), "crossed quote rejected");
    }
    Assert(!File.Exists(Path.Combine(directory, "invalid_quote.manifest.json")),
        "invalid run has no committed manifest");

    var reversedSource = source with { RunId = "reversed_time" };
    using (var writer = new TickExportWriter(directory, reversedSource, 3, DateTime.UtcNow))
    {
        writer.Add(first.AddMilliseconds(1), 1.1, 1.2);
        ExpectFailure(() => writer.Add(first, 1.1, 1.2), "reversed time rejected");
    }
    Assert(!File.Exists(Path.Combine(directory, "reversed_time.manifest.json")),
        "reversed run has no committed manifest");

    var boundedSource = source with { RunId = "bounded" };
    using (var writer = new TickExportWriter(directory, boundedSource, 1, DateTime.UtcNow))
    {
        writer.Add(first, 1.1, 1.2);
        ExpectFailure(() => writer.Add(first, 1.1, 1.2), "row limit rejected");
    }
    Assert(!File.Exists(Path.Combine(directory, "bounded.manifest.json")),
        "bounded run has no committed manifest");

    ExpectFailure(() => new TickExportWriter(directory, source with { RunId = "../unsafe" },
        3, DateTime.UtcNow), "unsafe run ID rejected");
    Console.WriteLine("tick export contract passed");
}
finally
{
    Directory.Delete(directory, recursive: true);
}

static void Assert(bool condition, string description)
{
    if (!condition)
        throw new Exception(description);
}

static void ExpectFailure(Action action, string description)
{
    try
    {
        action();
    }
    catch (ArgumentException) { return; }
    catch (InvalidDataException) { return; }
    catch (IOException) { return; }
    throw new Exception(description);
}
