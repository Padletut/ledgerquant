using LedgerQuant.LiveCapture;

var originalDirectory = Directory.GetCurrentDirectory();
var temporaryDirectory = Path.Combine(Path.GetTempPath(), "ledgerquant-journal-" + Guid.NewGuid());
Directory.CreateDirectory(temporaryDirectory);
try
{
    Directory.SetCurrentDirectory(temporaryDirectory);
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
