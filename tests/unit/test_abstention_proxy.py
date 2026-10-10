from datetime import datetime, timedelta, timezone

from ledgerquant.research.abstention_proxy import estimate_intent, score_day


def _time(minute: int) -> datetime:
    return datetime(2020, 2, 11, 8, 0, tzinfo=timezone.utc) + timedelta(minutes=minute)


def test_quote_counterfactual_uses_predecision_signal_and_bid_ask_round_trip():
    anchor = _time(30)
    quotes = [
        (_time(15) - timedelta(seconds=1), 99.0, 101.0),
        (anchor - timedelta(seconds=1), 101.0, 103.0),
        (anchor, 102.0, 104.0),
        (_time(45), 105.0, 107.0),
    ]
    assert estimate_intent(quotes, anchor) == ("LONG", 1.0)

    falling = [
        (_time(15) - timedelta(seconds=1), 105.0, 107.0),
        (anchor - timedelta(seconds=1), 101.0, 103.0),
        (anchor, 100.0, 102.0),
        (_time(45), 96.0, 98.0),
    ]
    assert estimate_intent(falling, anchor) == ("SHORT", 2.0)


def test_late_entry_is_not_assigned_a_fabricated_fill():
    anchor = _time(30)
    quotes = [
        (_time(15) - timedelta(seconds=1), 99.0, 100.0),
        (anchor - timedelta(seconds=1), 101.0, 102.0),
        (anchor + timedelta(seconds=6), 101.0, 102.0),
        (_time(45), 103.0, 104.0),
    ]
    assert estimate_intent(quotes, anchor) is None


def test_skip_uses_zero_executed_value_and_preserves_foregone_take_value():
    cases = [
        {"anchor_utc": _time(15).isoformat(), "status": "MEASURABLE", "forward_spread_p95": 0.1},
        {"anchor_utc": _time(30).isoformat(), "status": "MEASURABLE", "lookback_spread_iqr": 0.2},
        {"anchor_utc": _time(45).isoformat(), "status": "MEASURABLE"},
    ]
    quotes = [
        (_time(15) - timedelta(seconds=1), 99.0, 100.0),
        (_time(30) - timedelta(seconds=1), 101.0, 102.0),
        (_time(30), 101.0, 102.0),
        (_time(45), 99.0, 100.0),
    ]
    day = score_day("2020-02-11", cases, quotes, 0.085, 0.245)
    assert day["eligible_intents"] == 1
    assert day["all_take"] == {"taken": 1, "skipped": 0, "quote_pnl_per_ounce": -3.0}
    assert day["iqr_overlay"] == {"taken": 0, "skipped": 1, "quote_pnl_per_ounce": 0.0}
    assert day["recent_spread_baseline"] == day["all_take"]
    assert day["iqr_minus_all_take_per_ounce"] == 3.0
