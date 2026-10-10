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
