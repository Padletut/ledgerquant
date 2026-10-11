"""Point-in-time market context from the tick archive.

Only ticks with an event time at or before the decision time `T` are read. The bar
that contains `T` is cut off at `T` and marked incomplete. Prices are bid/ask mid
points; spreads are ask minus bid. Times are UTC.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import duckdb

from ledgerquant.replay.archive import ARCHIVE_VERSION

TIMEFRAMES = {"M5": timedelta(minutes=5), "H1": timedelta(hours=1), "D1": timedelta(days=1)}
DEFAULT_BARS = {"M5": 24, "H1": 24, "D1": 10}
INTERVAL_SQL = {"M5": "INTERVAL 5 MINUTE", "H1": "INTERVAL 1 HOUR", "D1": "INTERVAL 1 DAY"}


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("decision time must be timezone-aware")
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _iso(value: datetime) -> str:
    return value.replace(tzinfo=timezone.utc).isoformat()


def _text(value) -> str:
    return format(value.normalize(), "f") if isinstance(value, Decimal) else str(value)


class TickArchive:
    def __init__(self, archive_root: Path):
        self.root = Path(archive_root) / ARCHIVE_VERSION
        self.con = duckdb.connect()

    def _ticks(self, symbol: str, start: datetime, end: datetime) -> str:
        """SQL source for ticks in (start, end], pruned to the date partitions involved."""
        if not (self.root / f"symbol={symbol}").is_dir():
            raise FileNotFoundError(f"no archive for {symbol}")
        return (f"(SELECT * FROM read_parquet('{self.root}/symbol={symbol}/*/*.parquet', hive_partitioning = true) "
                f"WHERE date BETWEEN DATE '{start.date()}' AND DATE '{end.date()}' "
                f"AND event_time_utc > TIMESTAMP '{start}' AND event_time_utc <= TIMESTAMP '{end}')")

    def latest(self, symbol: str, at: datetime, lookback: timedelta = timedelta(days=5)) -> dict | None:
        t = _naive_utc(at)
        row = self.con.execute(f"""
            SELECT event_time_utc, bid, ask FROM {self._ticks(symbol, t - lookback, t)}
            ORDER BY event_time_utc DESC, source_run DESC, ordinal DESC LIMIT 1
        """).fetchone()
        if row is None:
            return None
        return {"id": f"quote:{symbol}:{_iso(row[0])}", "event_time_utc": _iso(row[0]),
                "bid": _text(row[1]), "ask": _text(row[2]),
                "spread": _text(row[2] - row[1]), "age_seconds": (t - row[0]).total_seconds()}

    def bars(self, symbol: str, at: datetime, timeframe: str, count: int) -> list[dict]:
        t = _naive_utc(at)
        step = TIMEFRAMES[timeframe]
        # Enough calendar time to cover weekends and holidays before taking the last `count` bars.
        start = t - step * count * 2 - timedelta(days=4)
        rows = self.con.execute(f"""
            SELECT time_bucket({INTERVAL_SQL[timeframe]}, event_time_utc) AS open_time,
                   arg_min((bid + ask) / 2, event_time_utc) AS open,
                   max((bid + ask) / 2) AS high,
                   min((bid + ask) / 2) AS low,
                   arg_max((bid + ask) / 2, event_time_utc) AS close,
                   count(*) AS ticks,
                   avg(ask - bid) AS spread_avg,
                   max(ask - bid) AS spread_max
            FROM {self._ticks(symbol, start, t)}
            GROUP BY open_time ORDER BY open_time DESC LIMIT {int(count)}
        """).fetchall()
        bars = []
        for open_time, open_, high, low, close, ticks, spread_avg, spread_max in reversed(rows):
            bars.append({
                "id": f"bar:{symbol}:{timeframe}:{_iso(open_time)}", "open_time_utc": _iso(open_time), "open": _text(open_), "high": _text(high),
                "low": _text(low), "close": _text(close), "ticks": ticks,
                "spread_avg": _text(round(Decimal(spread_avg), 6)), "spread_max": _text(spread_max),
                "complete": open_time + step <= t,
            })
        return bars

    def context(self, symbol: str, at: datetime, max_quote_age: timedelta = timedelta(minutes=5),
                bar_counts: dict[str, int] | None = None) -> dict:
        latest = self.latest(symbol, at)
        if latest is None:
            status = "UNAVAILABLE"
        elif latest["age_seconds"] > max_quote_age.total_seconds():
            status = "STALE"
        else:
            status = "READY"
        counts = bar_counts or DEFAULT_BARS
        return {
            "symbol": symbol, "decision_at_utc": at.astimezone(timezone.utc).isoformat(), "status": status,
            "max_quote_age_seconds": max_quote_age.total_seconds(), "latest": latest,
            "bars": {tf: self.bars(symbol, at, tf, n) for tf, n in counts.items()} if latest else {},
            "source": f"replay:{ARCHIVE_VERSION}", "visibility": "backfilled ticks, visible at event time",
        }
