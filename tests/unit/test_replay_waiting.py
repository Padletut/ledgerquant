from datetime import datetime, timedelta, timezone

from ledgerquant.replay.waiting import start_wait, wake

AT = datetime(2026, 3, 2, 10, tzinfo=timezone.utc)


def context(bid, ask="", ranges=("0.0010",) * 24):
    bars = [{"high": str(1 + float(r)), "low": "1"} for r in ranges]
    return {"market": {"latest": {"bid": bid, "ask": ask or bid}, "bars": {"H1": bars}}}


def test_wait_lasts_until_the_recheck_time_clamped_to_one_to_24_hours():
    waiting = start_wait(AT, 180, context("1.1000"))
    assert wake(waiting, AT + timedelta(hours=2), context("1.1005"))[0] is None
    assert wake(waiting, AT + timedelta(hours=3), context("1.1005"))[0] == "RECHECK_DUE"
    assert start_wait(AT, 5, context("1.1"))["until_utc"] == (AT + timedelta(hours=1)).isoformat()
    assert start_wait(AT, 3000, context("1.1"))["until_utc"] == (AT + timedelta(hours=24)).isoformat()


def test_a_large_price_move_wakes_the_agent_early():
    waiting = start_wait(AT, 600, context("1.1000"))  # mean hourly range 0.0010
    assert wake(waiting, AT + timedelta(hours=1), context("1.1014")) == (None, "1.40")
    assert wake(waiting, AT + timedelta(hours=1), context("1.0985")) == ("PRICE_MOVE", "1.50")
