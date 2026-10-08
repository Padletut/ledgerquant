using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;

namespace LedgerQuant.LiveCapture;

internal sealed class CaptureJournal : IDisposable
{
    private static readonly UTF8Encoding Utf8 = new(false, true);
    private readonly string _dataPath;
    private readonly string _cursorPath;
    private readonly string _identityPath;
    private readonly long _maximumBytes;
    private readonly FileStream _instanceLock;
    private long _acknowledgedOffset;

    public CaptureJournal(string feedId, string sourceIdentity, long maximumBytes)
    {
        Directory.CreateDirectory("capture");
        _dataPath = Path.Combine("capture", feedId + ".ndjson");
        _cursorPath = Path.Combine("capture", feedId + ".cursor");
        _identityPath = Path.Combine("capture", feedId + ".identity");
        _maximumBytes = maximumBytes;
        _instanceLock = new FileStream(
            Path.Combine("capture", feedId + ".lock"), FileMode.OpenOrCreate,
            FileAccess.ReadWrite, FileShare.None);

        try
        {
            if (File.Exists(_identityPath))
            {
                if (File.ReadAllText(_identityPath, Utf8) != sourceIdentity)
                    throw new InvalidDataException("capture feed ID belongs to another source identity");
            }
            else
            {
                if (File.Exists(_dataPath) || File.Exists(_cursorPath))
                    throw new InvalidDataException("capture journal lacks its source identity file");
                using var identity = new FileStream(_identityPath, FileMode.CreateNew,
                    FileAccess.Write, FileShare.None, 4096, FileOptions.WriteThrough);
                var bytes = Utf8.GetBytes(sourceIdentity);
                identity.Write(bytes, 0, bytes.Length);
                identity.Flush(flushToDisk: true);
            }
            if (!File.Exists(_dataPath))
                File.WriteAllBytes(_dataPath, Array.Empty<byte>());
            var length = new FileInfo(_dataPath).Length;
            if (length > 0)
            {
                using var stream = new FileStream(_dataPath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
                stream.Seek(-1, SeekOrigin.End);
                if (stream.ReadByte() != '\n')
                    throw new InvalidDataException("capture journal has an incomplete final record");
            }

            if (File.Exists(_cursorPath) &&
                !long.TryParse(File.ReadAllText(_cursorPath), NumberStyles.None,
                    CultureInfo.InvariantCulture, out _acknowledgedOffset))
                throw new InvalidDataException("capture acknowledgement cursor is invalid");
            if (_acknowledgedOffset < 0 || _acknowledgedOffset > length)
                throw new InvalidDataException("capture acknowledgement cursor is outside the journal");
        }
        catch
        {
            _instanceLock.Dispose();
            throw;
        }
    }

    public long PendingBytes => new FileInfo(_dataPath).Length - _acknowledgedOffset;

    public void Append(string json)
    {
        var bytes = Utf8.GetBytes(json + "\n");
        using var stream = new FileStream(_dataPath, FileMode.Open, FileAccess.Write,
            FileShare.Read, 4096, FileOptions.WriteThrough);
        if (stream.Length + bytes.Length > _maximumBytes)
            throw new IOException("capture journal reached its configured size limit");
        stream.Seek(0, SeekOrigin.End);
        stream.Write(bytes, 0, bytes.Length);
        stream.Flush(flushToDisk: true);
    }

    public JournalBatch ReadBatch(int maximumRecords, int maximumBytes)
    {
        var records = new List<string>();
        using var stream = new FileStream(_dataPath, FileMode.Open, FileAccess.Read,
            FileShare.ReadWrite, 4096, FileOptions.SequentialScan);
        stream.Seek(_acknowledgedOffset, SeekOrigin.Begin);
        var endOffset = _acknowledgedOffset;
        var consumed = 0;
        var deferredCompleteLine = false;
        using var line = new MemoryStream();

        while (records.Count < maximumRecords)
        {
            var next = stream.ReadByte();
            if (next < 0)
                break;
            line.WriteByte((byte)next);
            if (line.Length > maximumBytes)
                throw new InvalidDataException("capture journal record exceeds batch size limit");
            if (next != '\n')
                continue;
            if (records.Count > 0 && consumed + line.Length > maximumBytes)
            {
                deferredCompleteLine = true;
                break;
            }
            records.Add(Utf8.GetString(line.GetBuffer(), 0, checked((int)line.Length - 1)));
            consumed += checked((int)line.Length);
            endOffset = stream.Position;
            line.SetLength(0);
        }

        if (!deferredCompleteLine && line.Length > 0 && stream.Position == stream.Length)
            throw new InvalidDataException("capture journal contains an incomplete record");
        return new JournalBatch(records, endOffset);
    }

    public void Acknowledge(long endOffset)
    {
        if (endOffset < _acknowledgedOffset || endOffset > new FileInfo(_dataPath).Length)
            throw new InvalidDataException("invalid capture acknowledgement offset");
        var temporaryPath = _cursorPath + ".tmp";
        var bytes = Utf8.GetBytes(endOffset.ToString(CultureInfo.InvariantCulture));
        using (var stream = new FileStream(temporaryPath, FileMode.Create,
                   FileAccess.Write, FileShare.None, 4096, FileOptions.WriteThrough))
        {
            stream.Write(bytes, 0, bytes.Length);
            stream.Flush(flushToDisk: true);
        }
        File.Move(temporaryPath, _cursorPath, overwrite: true);
        _acknowledgedOffset = endOffset;
    }

    public void Dispose() => _instanceLock.Dispose();
}

internal sealed class JournalBatch
{
    public JournalBatch(IReadOnlyList<string> records, long endOffset)
    {
        Records = records;
        EndOffset = endOffset;
    }

    public IReadOnlyList<string> Records { get; }
    public long EndOffset { get; }
}
