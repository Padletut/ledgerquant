import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "tick_export_batch", Path(__file__).parents[2] / "tools/tick_export_batch.py")
batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)

UTC = timezone.utc


def test_chunks_cover_interval_without_gaps_and_respect_seven_days():
    start, end = datetime(2025, 9, 1, tzinfo=UTC), datetime(2025, 9, 20, tzinfo=UTC)
    parts = batch.chunks(start, end, 7)
    assert parts[0].start == start and parts[-1].end == end
    assert all(a.end == b.start for a, b in zip(parts, parts[1:]))
    assert max(p.end - p.start for p in parts).days == 7
    import pytest
    with pytest.raises(ValueError):
        batch.chunks(start, end, 8)


def test_split_halves_and_run_ids_are_unique_per_attempt():
    chunk = batch.Chunk(datetime(2025, 9, 1, tzinfo=UTC), datetime(2025, 9, 3, tzinfo=UTC))
    first, second = chunk.halves()
    assert first.start == chunk.start and second.end == chunk.end and first.end == second.start
    assert chunk.run_id("XAUUSD", 1) == "xauusd_20250901T0000_20250903T0000"
    assert chunk.run_id("XAUUSD", 2).endswith("_r2")


def test_outcome_reads_export_markers():
    assert batch.outcome("x\nTICK_EXPORT_COMPLETE run_id=a rows=3")[0] == "COMPLETE"
    limit = ("TICK_EXPORT_FAILED run_id=a type=IOException message=Tick export reached its "
             "configured row limit.\nTICK_EXPORT_INCOMPLETE run_id=a reason=IOException rows=9")
    assert batch.outcome(limit)[0] == "ROW_LIMIT"
    assert batch.outcome("TICK_EXPORT_FAILED run_id=a type=InvalidDataException message=No warm-up")[0] == "FAILED"
    assert batch.outcome("still downloading")[0] == "PENDING"


def test_verify_requires_matching_rows_size_and_hash(tmp_path):
    data = b"ordinal,event_time_utc,bid,ask\n1,2025-09-01T00:00:00Z,1.1,1.2\n"
    (tmp_path / "r.ticks.csv").write_bytes(data)
    manifest = {"row_count": 1, "data_bytes": len(data), "data_sha256": hashlib.sha256(data).hexdigest()}
    (tmp_path / "r.manifest.json").write_text(json.dumps(manifest))
    assert batch.verify(tmp_path, "r") == manifest
    (tmp_path / "r.manifest.json").write_text(json.dumps(manifest | {"row_count": 2}))
    assert batch.verify(tmp_path, "r") is None
    assert batch.verify(tmp_path, "missing") is None


def test_cli_time_format():
    assert batch.cli_time(datetime(2019, 12, 31, tzinfo=UTC)) == "31/12/2019 00:00"


def test_redact_removes_login_email_and_account_number():
    log = ("Establishing connection using someone@example.com...\nLogin to 1234567...\n"
           "TICK_EXPORT_START run_id=a broker=IC account=1234567 live=True")
    clean = batch.redact(log, "someone@example.com", "1234567")
    assert "1234567" not in clean and "@" not in clean
    assert "TICK_EXPORT_START" in clean
    assert batch.redact("contact other.person@mail.example.org", "x@y.z", "1") == "contact <email>"


def test_cli_end_never_lies_in_the_future():
    chunk = batch.Chunk(datetime(2026, 10, 5, tzinfo=UTC), datetime(2026, 10, 9, tzinfo=UTC))
    now = datetime(2026, 10, 10, 22, 30, 15, tzinfo=UTC)
    assert batch.cli_end(chunk, 4, now) == datetime(2026, 10, 10, 21, 30, tzinfo=UTC)
    old = batch.Chunk(datetime(2025, 9, 1, tzinfo=UTC), datetime(2025, 9, 8, tzinfo=UTC))
    assert batch.cli_end(old, 4, now) == datetime(2025, 9, 12, tzinfo=UTC)


def test_cli_start_uses_short_warmup_then_full_margin_on_retry():
    tuesday = batch.Chunk(datetime(2026, 3, 3, tzinfo=UTC), datetime(2026, 3, 5, tzinfo=UTC))
    assert batch.cli_start(tuesday, 1, 4) == datetime(2026, 3, 2, tzinfo=UTC)
    monday = batch.Chunk(datetime(2026, 3, 2, tzinfo=UTC), datetime(2026, 3, 4, tzinfo=UTC))
    assert batch.cli_start(monday, 1, 4) == datetime(2026, 2, 27, tzinfo=UTC)  # Friday
    assert batch.cli_start(monday, 2, 4) == datetime(2026, 2, 26, tzinfo=UTC)


def test_next_attempt_skips_failed_runs(tmp_path):
    chunk = batch.Chunk(datetime(2026, 3, 2, tzinfo=UTC), datetime(2026, 3, 4, tzinfo=UTC))
    assert batch.next_attempt(tmp_path, "XAUUSD", chunk) == 1
    (tmp_path / (chunk.run_id("XAUUSD", 1) + ".cli.log")).write_text("failed")
    assert batch.next_attempt(tmp_path, "XAUUSD", chunk) == 2


def test_main_splits_row_limit_retries_failures_and_runs_in_parallel(tmp_path, monkeypatch):
    import sys
    import threading
    calls, active, peak, lock = [], [0], [0], threading.Lock()

    def fake_run(symbol, chunk, run_id, attempt, out, args, ctid, account):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
            calls.append((run_id, attempt))
        import time
        time.sleep(0.05)
        with lock:
            active[0] -= 1
        if chunk.end - chunk.start == batch.timedelta(days=2):
            return "ROW_LIMIT", "row limit"
        if run_id.endswith("T0000_20250903T0000") and attempt == 1:
            (out / f"{run_id}.cli.log").write_text("failed")
            return "FAILED", "warm-up missing"
        data = b"ordinal,event_time_utc,bid,ask\n1,t,1,2\n"
        (out / f"{run_id}.ticks.csv").write_bytes(data)
        (out / f"{run_id}.manifest.json").write_text(json.dumps(
            {"row_count": 1, "data_bytes": len(data), "data_sha256": hashlib.sha256(data).hexdigest()}))
        return "COMPLETE", "ok"

    monkeypatch.setattr(batch, "run_one", fake_run)
    monkeypatch.setattr(batch, "credentials", lambda: ("login", "1234567"))
    monkeypatch.setattr(sys, "argv", ["x", "--symbol", "XAUUSD", "--start", "2025-09-01", "--end", "2025-09-05",
                                      "--chunk-days", "2", "--parallel", "2", "--out", str(tmp_path)])
    batch.main()
    statuses = [json.loads(line)["status"] for line in (tmp_path / "batch.jsonl").read_text().splitlines()]
    assert statuses.count("ROW_LIMIT") == 2 and statuses.count("FAILED") == 1
    assert statuses.count("COMPLETE") == 4  # four one-day halves, one after a retry
    assert ("xauusd_20250902T0000_20250903T0000_r2", 2) in calls
    assert peak[0] == 2
