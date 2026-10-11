"""Shadow positions simulated tick by tick on the replay archive.

A LONG enters at the ask and exits at the bid; a SHORT enters at the bid and exits
at the ask. A stop or target is filled at the first tick that reaches it, at that
tick's price, so a gap past the level is filled worse than the level. When stop
and target are reached on the same tick, the stop counts. A position still open
at its maximum holding time closes at the last price before that time. Results
are in R: the move divided by the initial risk (entry to initial stop).
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from ledgerquant.replay.market import TickArchive, _naive_utc, _text


@dataclass
class Position:
    symbol: str
    direction: str  # LONG or SHORT
    opened_at: datetime
    entry: Decimal
    stop: Decimal
    target: Decimal
    close_by: datetime
    decision_id: str
    initial_stop: Decimal = None
    checked_until: datetime = None
    adjustments: list = field(default_factory=list)

    def __post_init__(self):
        self.initial_stop = self.initial_stop if self.initial_stop is not None else self.stop
        self.checked_until = self.checked_until or self.opened_at

    @property
    def sign(self) -> int:
        return 1 if self.direction == "LONG" else -1

    def r(self, price: Decimal) -> Decimal:
        risk = self.sign * (self.entry - self.initial_stop)
        return (self.sign * (price - self.entry) / risk).quantize(Decimal("0.0001"))

    def state(self, mark: Decimal | None) -> dict:
        return {"direction": self.direction, "opened_at_utc": self.opened_at.isoformat(), "entry": str(self.entry),
                "stop": str(self.stop), "target": str(self.target), "close_by_utc": self.close_by.isoformat(),
                "initial_stop": str(self.initial_stop),
                "current_r": str(self.r(mark)) if mark is not None else None}


def exit_side(direction: str) -> str:
    return "bid" if direction == "LONG" else "ask"


def advance(archive: TickArchive, position: Position, until: datetime) -> dict | None:
    """Move the position forward to `until`; return the exit if it closed on the way."""
    end = min(until, position.close_by)
    if end <= position.checked_until:
        return None
    side = exit_side(position.direction)
    stop_cond = f"{side} <= {position.stop}" if position.direction == "LONG" else f"{side} >= {position.stop}"
    target_cond = f"{side} >= {position.target}" if position.direction == "LONG" else f"{side} <= {position.target}"
    source = archive._ticks(position.symbol, _naive_utc(position.checked_until), _naive_utc(end))
    hit = archive.con.execute(f"""
        SELECT event_time_utc, {side}, CASE WHEN {stop_cond} THEN 'STOP' ELSE 'TARGET' END
        FROM {source} WHERE ({stop_cond}) OR ({target_cond})
        ORDER BY event_time_utc, source_run, ordinal LIMIT 1
    """).fetchone()
    if hit:
        at, price, reason = hit
        return close(position, at.replace(tzinfo=timezone.utc), Decimal(price), reason)
    position.checked_until = end
    if end >= position.close_by:
        latest = archive.latest(position.symbol, position.close_by)
        price = Decimal(latest[side]) if latest else position.entry
        return close(position, position.close_by, price, "MAX_HOLDING_TIME")
    return None


def close(position: Position, at: datetime, price: Decimal, reason: str) -> dict:
    return {"symbol": position.symbol, "direction": position.direction, "decision_id": position.decision_id,
            "opened_at_utc": position.opened_at.isoformat(), "closed_at_utc": at.isoformat(),
            "entry": _text(position.entry), "exit": _text(price), "initial_stop": _text(position.initial_stop),
            "final_stop": _text(position.stop), "target": _text(position.target), "exit_reason": reason,
            "r": str(position.r(price)), "adjustments": position.adjustments}


def static_outcome(archive: TickArchive, symbol: str, direction: str, opened_at: datetime, entry: Decimal,
                   stop: Decimal, target: Decimal, close_by: datetime) -> dict:
    """The same levels held without any review: the static-exit comparison."""
    shadow = Position(symbol, direction, opened_at, entry, stop, target, close_by, "static")
    return advance(archive, shadow, close_by)


def mirrored(archive: TickArchive, trade_open: dict, symbol: str) -> dict:
    """The opposite direction with the same stop and target distances, held statically."""
    direction = "SHORT" if trade_open["direction"] == "LONG" else "LONG"
    latest = trade_open["quote"]
    entry = Decimal(latest["ask"] if direction == "LONG" else latest["bid"])
    stop_distance = abs(Decimal(trade_open["entry"]) - Decimal(trade_open["stop"]))
    target_distance = abs(Decimal(trade_open["target"]) - Decimal(trade_open["entry"]))
    sign = 1 if direction == "LONG" else -1
    opened = datetime.fromisoformat(trade_open["opened_at_utc"])
    return static_outcome(archive, symbol, direction, opened, entry, entry - sign * stop_distance,
                          entry + sign * target_distance, datetime.fromisoformat(trade_open["close_by_utc"]))
