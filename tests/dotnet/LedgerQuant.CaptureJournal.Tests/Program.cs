using LedgerQuant.LiveCapture;

var originalDirectory = Directory.GetCurrentDirectory();
var temporaryDirectory = Path.Combine(Path.GetTempPath(), "ledgerquant-journal-" + Guid.NewGuid());
Directory.CreateDirectory(temporaryDirectory);
try
{
    Directory.SetCurrentDirectory(temporaryDirectory);
    Assert(CaptureFeedId.Create("icm_live_12345_", "EURUSD") ==
           "icm_live_12345_eurusd", "existing EURUSD feed ID is preserved");
    Assert(CaptureFeedId.Create("icm_live_12345_", "US 500") ==
           "icm_live_12345_us_20500", "non-alphanumeric symbol bytes are escaped");
    Assert(CaptureFeedId.Create("icm_live_12345_", "US_20500") !=
           CaptureFeedId.Create("icm_live_12345_", "US 500"),
           "escaped symbol names do not collide");
    ExpectArgument(() => CaptureFeedId.Create("", "EURUSD"),
        "empty prefix rejected");
    ExpectArgument(() => CaptureFeedId.Create("bad prefix", "EURUSD"),
        "unsafe prefix rejected");
    ExpectArgument(() => CaptureFeedId.Create(new string('x', 95), "EURUSD"),
        "feed ID over protocol limit rejected");

    using (var journal = new CaptureJournal("test_feed", "source-one", 1024))
    {
        journal.Append("{\"sequence\":1}");
        journal.Append("{\"sequence\":2}");
        var first = journal.ReadBatch(10, 20);
        Assert(first.Records.Count == 1 && first.Records[0].Contains(":1}"),
            "first batch identity");
        journal.Acknowledge(first.EndOffset);
        Assert(journal.PendingBytes > 0, "unacknowledged record retained");
    }

    using (var eurusd = new CaptureJournal("account_eurusd", "eurusd-source", 1024))
    using (var gbpusd = new CaptureJournal("account_gbpusd", "gbpusd-source", 1024))
    {
        eurusd.Append("{\"symbol\":\"EURUSD\"}");
        gbpusd.Append("{\"symbol\":\"GBPUSD\"}");
        var eurusdBatch = eurusd.ReadBatch(10, 1024);
        eurusd.Acknowledge(eurusdBatch.EndOffset);
        Assert(eurusd.PendingBytes == 0 && gbpusd.PendingBytes > 0,
            "acknowledging one feed does not advance another feed");
    }

    using (var recovered = new CaptureJournal("test_feed", "source-one", 1024))
    {
        var second = recovered.ReadBatch(10, 20);
        Assert(second.Records.Count == 1 && second.Records[0].Contains(":2}"),
            "restart resumes after acknowledged cursor");
        recovered.Acknowledge(second.EndOffset);
        Assert(recovered.PendingBytes == 0, "all records acknowledged");
    }

    try
    {
        using var invalid = new CaptureJournal("test_feed", "source-two", 1024);
        throw new Exception("feed source identity changed without rejection");
    }
    catch (InvalidDataException)
    {
    }

    using (var journal = new CaptureJournal("test_feed", "source-one", 1024))
    {
        File.AppendAllText(Path.Combine("capture", "test_feed.ndjson"), "partial");
        try
        {
            journal.ReadBatch(10, 1024);
            throw new Exception("partial record was acknowledged");
        }
        catch (InvalidDataException)
        {
        }
    }

    Console.WriteLine("capture journal contract passed");
}
finally
{
    Directory.SetCurrentDirectory(originalDirectory);
    Directory.Delete(temporaryDirectory, recursive: true);
}

static void Assert(bool condition, string description)
{
    if (!condition)
        throw new Exception(description);
}

static void ExpectArgument(Action action, string description)
{
    try
    {
        action();
        throw new Exception(description);
    }
    catch (ArgumentException)
    {
    }
}
