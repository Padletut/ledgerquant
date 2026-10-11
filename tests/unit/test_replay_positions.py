from datetime import datetime, timedelta, timezone
from decimal import Decimal

from ledgerquant.replay.archive import build_symbol
from ledgerquant.replay.market import TickArchive
from ledgerquant.replay.positions import Position, advance, mirrored, static_outcome
from tests.unit.test_replay_market import export

UTC = timezone.utc


def t(minute, second=0):
    return datetime(2026, 3, 2, 10, minute, second)


def archive(tmp_path, ticks):
    export(tmp_path / "exports", "run_a", "2026-03-02", "2026-03-03", ticks)
    build_symbol(tmp_path / "exports", tmp_path / "archive", "EURUSD")
    return TickArchive(tmp_path / "archive")


def long(stop="1.0990", target="1.1020", close_by=None):
    opened = datetime(2026, 3, 2, 10, 0, tzinfo=UTC)
    return Position("EURUSD", "LONG", opened, Decimal("1.1000"), Decimal(stop), Decimal(target),
                    close_by or opened + timedelta(hours=4), "d1")


def test_stop_fills_at_the_gap_price_and_counts_before_target(tmp_path):
    store = archive(tmp_path, [(t(0, 1), "1.1001", "1.1002"), (t(5), "1.0980", "1.0981"), (t(6), "1.1030", "1.1031")])
    exit_ = advance(store, long(), datetime(2026, 3, 2, 11, 0, tzinfo=UTC))
    assert exit_["exit_reason"] == "STOP" and exit_["exit"] == "1.098" and exit_["r"] == "-2.0000"


def test_target_and_open_position_progress(tmp_path):
    store = archive(tmp_path, [(t(1), "1.1005", "1.1006"), (t(20), "1.1021", "1.1022"), (t(50), "1.0900", "1.0901")])
    position = long()
    assert advance(store, position, datetime(2026, 3, 2, 10, 10, tzinfo=UTC)) is None
    assert position.checked_until == datetime(2026, 3, 2, 10, 10, tzinfo=UTC)
    exit_ = advance(store, position, datetime(2026, 3, 2, 11, 0, tzinfo=UTC))
    assert exit_["exit_reason"] == "TARGET" and exit_["r"] == "2.1000"


def test_maximum_holding_time_closes_at_the_last_price(tmp_path):
    store = archive(tmp_path, [(t(1), "1.1005", "1.1006"), (t(30), "1.1008", "1.1009")])
    position = long(close_by=datetime(2026, 3, 2, 10, 40, tzinfo=UTC))
    exit_ = advance(store, position, datetime(2026, 3, 2, 12, 0, tzinfo=UTC))
    assert exit_["exit_reason"] == "MAX_HOLDING_TIME" and exit_["exit"] == "1.1008"
    assert exit_["closed_at_utc"].startswith("2026-03-02T10:40")


def test_static_and_mirrored_outcomes(tmp_path):
    store = archive(tmp_path, [(t(1), "1.1005", "1.1006"), (t(20), "1.0985", "1.0986")])
    opened = datetime(2026, 3, 2, 10, 0, tzinfo=UTC)
    close_by = opened + timedelta(hours=2)
    static = static_outcome(store, "EURUSD", "LONG", opened, Decimal("1.1000"), Decimal("1.0990"),
                            Decimal("1.1020"), close_by)
    assert static["exit_reason"] == "STOP"
    mirror = mirrored(store, {"direction": "LONG", "entry": "1.1000", "stop": "1.0990", "target": "1.1020",
                              "opened_at_utc": opened.isoformat(), "close_by_utc": close_by.isoformat(),
                              "quote": {"bid": "1.0999", "ask": "1.1000"}}, "EURUSD")
    # SHORT at 1.0999, stop 1.1009, target 1.0979: never reached, closes at the last ask
    assert mirror["direction"] == "SHORT" and mirror["exit_reason"] == "MAX_HOLDING_TIME"
    assert mirror["exit"] == "1.0986" and mirror["r"] == "1.3000"
