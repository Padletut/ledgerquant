import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from ledgerquant.replay.archive import ArchiveError, build_symbol
from ledgerquant.replay.market import TickArchive

UTC = timezone.utc


def export(directory, run_id, start, end, ticks):
    """Write a TickExport-shaped CSV and manifest; ticks are (datetime, bid, ask)."""
    directory.mkdir(parents=True, exist_ok=True)
    lines = ["ordinal,event_time_utc,bid,ask"] + [
        f"{i},{t.strftime('%Y-%m-%dT%H:%M:%S.%f')}0Z,{bid},{ask}" for i, (t, bid, ask) in enumerate(ticks, 1)]
    data = ("\n".join(lines) + "\n").encode()
    (directory / f"{run_id}.ticks.csv").write_bytes(data)
    (directory / f"{run_id}.manifest.json").write_text(json.dumps({
        "run_id": run_id, "broker_symbol": "EURUSD", "data_file": f"{run_id}.ticks.csv",
        "requested_start_utc": start + "T00:00:00.0000000Z", "requested_end_exclusive_utc": end + "T00:00:00.0000000Z",
        "row_count": len(ticks), "data_bytes": len(data), "data_sha256": hashlib.sha256(data).hexdigest()}))


def at(hour, minute=0, second=0, day=2):
    return datetime(2026, 3, day, hour, minute, second)


@pytest.fixture
def archive(tmp_path):
    exports = tmp_path / "exports"
    export(exports, "run_a", "2026-03-02", "2026-03-03", [
        (at(9, 0, 1), "1.10000", "1.10010"),
        (at(9, 30), "1.10100", "1.10110"),
        (at(9, 59, 59), "1.10050", "1.10060"),
        (at(10, 0), "1.10200", "1.10210"),      # exactly at the decision time below
        (at(10, 0, 1), "1.19000", "1.19010"),   # one second later: must stay invisible
        (at(10, 20), "1.20000", "1.20010"),
    ])
    export(exports, "run_b", "2026-03-03", "2026-03-04", [(at(9, 0, day=3), "1.30000", "1.30010")])
    manifest = build_symbol(exports, tmp_path / "archive", "EURUSD")
    return TickArchive(tmp_path / "archive"), manifest


def test_archive_keeps_every_row_and_records_sources(archive):
    _, manifest = archive
    assert manifest["rows"] == 7
    assert [s["run_id"] for s in manifest["sources"]] == ["run_a", "run_b"]
    assert manifest["start_utc"] == "2026-03-02T00:00:00" and manifest["end_exclusive_utc"] == "2026-03-04T00:00:00"


def test_latest_quote_never_comes_from_after_the_decision_time(archive):
    store, _ = archive
    t = datetime(2026, 3, 2, 10, 0, tzinfo=UTC)
    latest = store.latest("EURUSD", t)
    assert latest["bid"] == "1.102" and latest["age_seconds"] == 0
    assert store.latest("EURUSD", t - timedelta(seconds=1))["bid"] == "1.1005"


def test_forming_bar_is_cut_at_decision_time_and_marked_incomplete(archive):
    store, _ = archive
    t = datetime(2026, 3, 2, 10, 0, 30, tzinfo=UTC)
    h1 = store.bars("EURUSD", t, "H1", 5)
    assert [b["open_time_utc"][11:16] for b in h1] == ["09:00", "10:00"]
    nine, ten = h1
    assert nine["complete"] and nine["ticks"] == 3
    assert (nine["open"], nine["high"], nine["low"], nine["close"]) == ("1.10005", "1.10105", "1.10005", "1.10055")
    assert not ten["complete"] and ten["ticks"] == 2 and ten["high"] == "1.19005"
    assert all(b["ticks"] < 4 for b in store.bars("EURUSD", t, "M5", 30))


def test_context_status_reflects_quote_age_and_missing_data(archive):
    store, _ = archive
    ready = store.context("EURUSD", datetime(2026, 3, 2, 10, 21, tzinfo=UTC))
    assert ready["status"] == "READY" and ready["bars"]["H1"][-1]["open_time_utc"].startswith("2026-03-02T10:00")
    assert store.context("EURUSD", datetime(2026, 3, 2, 12, 0, tzinfo=UTC))["status"] == "STALE"
    empty = store.context("EURUSD", datetime(2026, 2, 20, 12, 0, tzinfo=UTC))
    assert empty["status"] == "UNAVAILABLE" and empty["bars"] == {}
    with pytest.raises(ValueError):
        store.latest("EURUSD", datetime(2026, 3, 2, 10, 0))


def test_tampered_or_overlapping_exports_are_refused(tmp_path):
    exports = tmp_path / "exports"
    export(exports, "run_a", "2026-03-02", "2026-03-04", [(at(9), "1.1", "1.1")])
    export(exports, "run_b", "2026-03-03", "2026-03-05", [(at(9, day=3), "1.1", "1.1")])
    with pytest.raises(ArchiveError, match="overlap"):
        build_symbol(exports, tmp_path / "archive", "EURUSD")
    (exports / "run_b.manifest.json").unlink()
    with (exports / "run_a.ticks.csv").open("a") as handle:
        handle.write("2,2026-03-02T09:00:01.0000000Z,9.9,9.9\n")
    with pytest.raises(ArchiveError, match="does not match"):
        build_symbol(exports, tmp_path / "archive", "EURUSD")
