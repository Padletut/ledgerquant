"""When to ask the agent again after it chose WAIT.

The agent states how long it wants to wait (`recheck_after_minutes`). Without an
open position the run does not call the model again until that time has passed,
clamped to MIN_RECHECK..MAX_RECHECK, unless the price wakes it earlier: a move of
WAKE_RANGES times the mean hourly range (from the 24 hourly bars the agent saw at
the WAIT) away from the mid at the WAIT. The check is deterministic and free;
NO_SIGNAL and open positions are still reviewed at every decision time.
"""

from datetime import datetime, timedelta
from decimal import Decimal

MIN_RECHECK, MAX_RECHECK = timedelta(minutes=60), timedelta(hours=24)
WAKE_RANGES = Decimal("1.5")


def _mid(context: dict) -> Decimal:
    latest = context["market"]["latest"]
    return (Decimal(latest["bid"]) + Decimal(latest["ask"])) / 2


def start_wait(at: datetime, recheck_after_minutes: int, context: dict) -> dict:
    h1 = context["market"]["bars"].get("H1") or []
    mean_range = sum(Decimal(b["high"]) - Decimal(b["low"]) for b in h1) / len(h1) if h1 else None
    delay = min(max(timedelta(minutes=recheck_after_minutes), MIN_RECHECK), MAX_RECHECK)
    return {"since_utc": at.isoformat(), "until_utc": (at + delay).isoformat(), "mid": str(_mid(context)),
            "mean_h1_range": str(mean_range) if mean_range else None}


def wake(waiting: dict, at: datetime, context: dict) -> tuple[str | None, str | None]:
    """The reason to call the agent now (RECHECK_DUE or PRICE_MOVE), or None to keep waiting; and the move in ranges."""
    move = None
    if waiting["mean_h1_range"]:
        move = abs(_mid(context) - Decimal(waiting["mid"])) / Decimal(waiting["mean_h1_range"])
    if at >= datetime.fromisoformat(waiting["until_utc"]):
        return "RECHECK_DUE", str(move.quantize(Decimal("0.01"))) if move is not None else None
    if move is not None and move >= WAKE_RANGES:
        return "PRICE_MOVE", str(move.quantize(Decimal("0.01")))
    return None, str(move.quantize(Decimal("0.01"))) if move is not None else None
