from datetime import datetime, timezone
from decimal import Decimal

from ledgerquant.replay.costs import (annual_swap, next_rollover, policy_rates, rollovers_between, swap_context, swap_r,
                                      time_context, weekend_close)

UTC = timezone.utc
RATES = {"USD": Decimal("0.04"), "EUR": Decimal("0.02"), "GBP": Decimal("0.04")}


def test_rollover_follows_new_york_time_and_skips_weekends():
    assert next_rollover(datetime(2025, 9, 10, 20, tzinfo=UTC)) == datetime(2025, 9, 10, 21, tzinfo=UTC)  # summer
    assert next_rollover(datetime(2025, 11, 12, 14, tzinfo=UTC)) == datetime(2025, 11, 12, 22, tzinfo=UTC)  # winter
    assert next_rollover(datetime(2025, 11, 14, 23, tzinfo=UTC)) == datetime(2025, 11, 17, 22, tzinfo=UTC)  # Fri -> Mon
    assert weekend_close(datetime(2025, 11, 12, 14, tzinfo=UTC)) == datetime(2025, 11, 14, 22, tzinfo=UTC)


def test_wednesday_rollover_counts_three_days():
    days = [d for _, d in rollovers_between(datetime(2025, 11, 10, 9, tzinfo=UTC), datetime(2025, 11, 14, 9, tzinfo=UTC))]
    assert days == [1, 1, 3, 1]
    assert time_context(datetime(2025, 11, 12, 14, tzinfo=UTC))["next_rollover_days_charged"] == 3


def test_swap_is_carry_minus_the_calibrated_markup():
    from ledgerquant.replay.costs import markups
    for symbol, carry in (("EURUSD", Decimal("-0.02")), ("GBPUSD", Decimal("0")), ("XAUUSD", Decimal("-0.04"))):
        markup, calibrated = markups(symbol)
        assert calibrated, f"{symbol} should have broker terms"
        swap = annual_swap(symbol, RATES)
        assert swap["LONG"] == carry - markup["LONG"] and swap["SHORT"] == -carry - markup["SHORT"]
    macro = {"series": {"DFEDTARU": [{"value": "4"}], "ECBDFR": [{"value": "2"}], "IUDSOIA": [{"value": "4"}]}}
    assert "calibrated from broker terms" in swap_context("EURUSD", Decimal("1.16"), macro)["basis"]


def test_symbols_without_terms_use_the_labelled_default(monkeypatch):
    import ledgerquant.replay.costs as costs
    monkeypatch.setattr(costs, "broker_terms", lambda: {})
    markup, calibrated = costs.markups("XAUUSD")
    assert not calibrated and markup == {"LONG": costs.DEFAULT_MARKUP, "SHORT": costs.DEFAULT_MARKUP}


def test_commission_is_thirty_usd_per_million_per_side():
    from ledgerquant.replay.costs import commission_r
    # 1.1000 and 1.1010 at 30 per million: 0.000033 + 0.00003303 = 0.00006603 over a 0.0010 risk
    assert commission_r("EURUSD", Decimal("1.1000"), Decimal("1.1010"), Decimal("1.0990")) == Decimal("-0.0660")


def test_swap_in_r_over_a_held_week_and_missing_rates():
    opened, closed = datetime(2025, 11, 10, 9, tzinfo=UTC), datetime(2025, 11, 14, 9, tzinfo=UTC)
    # 6 days (Wednesday counts three) of the long swap rate on 4100, over a 20 risk
    expected = (Decimal("4100") * annual_swap("XAUUSD", RATES)["LONG"] / 360 * 6 / 20).quantize(Decimal("0.0001"))
    assert swap_r("XAUUSD", "LONG", Decimal("4100"), Decimal("4080"), opened, closed, RATES) == expected < 0
    assert swap_r("XAUUSD", "LONG", Decimal("4100"), Decimal("4080"), opened, closed, None) == 0
    macro = {"series": {"DFEDTARU": [{"value": "4.00"}], "ECBDFR": [{"value": "2.00"}]}}
    assert policy_rates(macro) is None
    assert swap_context("EURUSD", Decimal("1.16"), macro)["status"] == "UNAVAILABLE"
