"""Market times and an estimated overnight swap for replay.

Times (declared assumptions, not yet verified against IC Markets' schedule):

- Rollover is 17:00 New York time on each trading day: 21:00 UTC in US summer
  time, 22:00 UTC in winter. Wednesday's rollover counts three days (it covers
  the weekend), as is usual for FX.
- The weekly close is Friday 17:00 New York time.

Swap estimate: the annual carry of a position from central-bank rates visible at
the decision time, minus a broker markup on either side. EURUSD and GBPUSD earn
the base rate and pay the quote rate when long, and the reverse when short.
XAUUSD long pays the USD rate (gold lease income taken as zero); short earns it.
Rates: USD = Fed funds target upper bound (DFEDTARU), EUR = ECB deposit rate
(ECBDFR), GBP = SONIA (IUDSOIA). The markup is an assumption to calibrate with
the broker's published swap rates; historical broker swaps are not available.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")
MARKUP_ANNUAL = Decimal("0.015")
DAY_BASIS = {"EURUSD": 360, "GBPUSD": 365, "XAUUSD": 360}
RATE_SERIES = {"USD": "DFEDTARU", "EUR": "ECBDFR", "GBP": "IUDSOIA"}
PAIRS = {"EURUSD": ("EUR", "USD"), "GBPUSD": ("GBP", "USD"), "XAUUSD": (None, "USD")}


def _at_ny(t: datetime, days: int, hour: int = 17) -> datetime:
    local = t.astimezone(NEW_YORK)
    return (local + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)


def next_rollover(t: datetime) -> datetime:
    """The first rollover strictly after `t`, on a weekday."""
    for days in range(0, 8):
        candidate = _at_ny(t, days)
        if candidate > t.astimezone(NEW_YORK) and candidate.weekday() < 5:
            return candidate.astimezone(timezone.utc)
    raise AssertionError("no rollover within a week")


def weekend_close(t: datetime) -> datetime:
    """The first Friday 17:00 New York time strictly after `t`."""
    local = t.astimezone(NEW_YORK)
    close = _at_ny(t, (4 - local.weekday()) % 7)
    return (close if close > local else close + timedelta(days=7)).astimezone(timezone.utc)


def rollover_days(rollover: datetime) -> int:
    return 3 if rollover.astimezone(NEW_YORK).weekday() == 2 else 1


def rollovers_between(start: datetime, end: datetime) -> list[tuple[datetime, int]]:
    """Rollovers in (start, end] with the number of days each one charges."""
    found, current = [], next_rollover(start)
    while current <= end:
        found.append((current, rollover_days(current)))
        current = next_rollover(current)
    return found


def time_context(t: datetime) -> dict:
    roll, close = next_rollover(t), weekend_close(t)
    return {
        "next_rollover_utc": roll.isoformat(), "hours_to_rollover": round((roll - t).total_seconds() / 3600, 2),
        "next_rollover_days_charged": rollover_days(roll),
        "weekend_close_utc": close.isoformat(), "hours_to_weekend_close": round((close - t).total_seconds() / 3600, 2),
        "basis": "rollover and weekly close at 17:00 New York time (assumed); Wednesday rollover counts three days",
    }


def policy_rates(macro: dict) -> dict[str, Decimal] | None:
    """Latest visible policy rates as fractions, or None when one is missing."""
    rates = {}
    for currency, series in RATE_SERIES.items():
        observations = (macro.get("series") or {}).get(series)
        if not observations:
            return None
        rates[currency] = Decimal(observations[-1]["value"]) / 100
    return rates


def annual_swap(symbol: str, rates: dict[str, Decimal]) -> dict[str, Decimal]:
    """Estimated annual swap rate for each direction, as a fraction of the position's value."""
    base, quote = PAIRS[symbol]
    carry = (rates[base] if base else Decimal(0)) - rates[quote]
    return {"LONG": carry - MARKUP_ANNUAL, "SHORT": -carry - MARKUP_ANNUAL}


def swap_per_day(symbol: str, direction: str, price: Decimal, rates: dict[str, Decimal]) -> Decimal:
    """Estimated swap per day in price units for one unit; negative is a cost."""
    return price * annual_swap(symbol, rates)[direction] / DAY_BASIS[symbol]


def swap_context(symbol: str, price: Decimal, macro: dict) -> dict:
    rates = policy_rates(macro)
    if rates is None:
        return {"status": "UNAVAILABLE", "reason": "a policy rate is not visible at the decision time"}
    swaps = annual_swap(symbol, rates)
    return {
        "status": "ESTIMATED",
        **{direction: {"annual_pct": str((swaps[direction] * 100).quantize(Decimal("0.01"))),
                       "per_day_price": str(swap_per_day(symbol, direction, price, rates).quantize(Decimal("0.000001")))}
           for direction in ("LONG", "SHORT")},
        "basis": f"policy-rate differential minus an assumed {MARKUP_ANNUAL * 100}% broker markup; negative is a cost",
    }


def swap_r(symbol: str, direction: str, entry: Decimal, initial_stop: Decimal, opened: datetime,
           closed: datetime, rates: dict[str, Decimal] | None) -> Decimal:
    """Swap accrued between opening and closing, in R; zero when rates are unknown."""
    if rates is None:
        return Decimal(0)
    days = sum(charge for _, charge in rollovers_between(opened, closed))
    risk = abs(entry - initial_stop)
    return (swap_per_day(symbol, direction, entry, rates) * days / risk).quantize(Decimal("0.0001"))
