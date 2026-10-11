"""News, macro and calendar context visible at a decision time, from the replay snapshot.

Visibility rules (architecture, Section 5.2):

- A news item is visible from its real `available_at`. A backfilled GDELT item has
  none and is treated as visible 15 minutes after its GKG batch time.
- An ALFRED vintage is visible from the start of the UTC day after its
  `realtime_start` date, because release times are not recorded.
- The release calendar is the schedule as captured; a reschedule announced after
  `T` may already show. This is stated in the context.

Which items are shown is a context recipe, versioned so Research can change it.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb

from ledgerquant.replay.snapshot import SNAPSHOT_VERSION

NEWS_RECIPE = "news_recipe_v1"  # keyword patterns per instrument; change the version when they change
BACKFILL_VISIBILITY = timedelta(minutes=15)
CENTRAL_BANK_SOURCES = ("fed_press", "ecb_press", "boe_news")
_MOVE = r"(falls?|rises?|slips?|gains?|hits?|climbs?|drops?|steady|steadies|edges?|jumps?|slides?|tumbles?|rall(y|ies)|record|weakens?|strengthens?)"
_USD = (r"\b(u\.?s\.? dollar|dollar index|greenback|dollar " + _MOVE + r"|federal reserve|fomc|powell"
        r"|fed (rate|chair|officials?|policy|minutes|cut|hike|decision)|treasury yields?"
        r"|u\.?s\.? (inflation|cpi|jobs|payrolls|economy|gdp|tariffs?|retail sales)|nonfarm|payrolls)")
_EUR = r"\b(eurozone|euro (zone|area)|euro " + _MOVE + r"|eur/usd|eurusd|ecb|lagarde|bund yields?)"
_GBP = (r"\b(sterling|pound " + _MOVE + r"|gbp/usd|cable|bank of england|boe|bailey"
        r"|uk (inflation|economy|gdp|jobs|wages)|gilts?)\b")
_GOLD = r"\b(gold (price|prices|futures)|gold " + _MOVE + r"|spot gold|bullion|precious metals?|xau)"
INSTRUMENT_PATTERNS = {"EURUSD": f"{_EUR}|{_USD}", "GBPUSD": f"{_GBP}|{_USD}", "XAUUSD": f"{_GOLD}|{_USD}"}
# Releases that are scheduled events; daily data updates (rates, yields, FX) are left out.
EVENT_RELEASES = {9: "Retail sales", 10: "US CPI", 50: "US employment", 53: "US GDP", 54: "US PCE",
                  180: "US initial claims", 251: "Euro area HICP"}
MACRO_SERIES = ("CPIAUCSL", "CPILFESL", "PCEPILFE", "PAYEMS", "UNRATE", "ICSA", "RSAFS", "GDPC1",
                "DFEDTARU", "DGS10", "DTWEXBGS", "ECBDFR", "CP0000EZ19M086NEST", "IUDSOIA")


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("decision time must be timezone-aware")
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _iso(value) -> str | None:
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


class NewsArchive:
    def __init__(self, archive_root: Path):
        self.root = Path(archive_root) / SNAPSHOT_VERSION
        self.con = duckdb.connect()
        self.items = f"read_parquet('{self.root}/news_items.parquet')"

    def _visible(self, t: datetime) -> str:
        return (f"(coalesce(available_at, CASE WHEN backfilled AND source = 'gdelt_gkg' "
                f"THEN published_at + INTERVAL {int(BACKFILL_VISIBILITY.total_seconds())} SECOND END) "
                f"<= TIMESTAMP '{t}')")

    def news(self, symbol: str, at: datetime, hours: int = 6, limit: int = 25, central_bank_days: int = 7,
             central_bank_limit: int = 10) -> dict:
        t = _naive_utc(at)
        rows = self.con.execute(f"""
            SELECT any_value(published_at) AS published_at, any_value(source) AS source, title,
                   any_value(url) AS url, any_value(details) AS details
            FROM {self.items}
            WHERE source = 'gdelt_gkg' AND published_at > TIMESTAMP '{t - timedelta(hours=hours)}'
              AND published_at <= TIMESTAMP '{t}' AND {self._visible(t)}
              AND regexp_matches(lower(title), $pattern)
            GROUP BY title ORDER BY max(published_at) DESC LIMIT {int(limit)}
        """, {"pattern": INSTRUMENT_PATTERNS[symbol]}).fetchall()
        banks = self.con.execute(f"""
            SELECT published_at, source, title, url, summary FROM {self.items}
            WHERE source IN {CENTRAL_BANK_SOURCES} AND {self._visible(t)}
              AND published_at > TIMESTAMP '{t - timedelta(days=central_bank_days)}'
            ORDER BY published_at DESC LIMIT {int(central_bank_limit)}
        """).fetchall()
        headlines = []
        for published, source, title, url, details in rows:
            info = json.loads(details or "{}")
            tone = (info.get("tone") or "").split(",")[0]
            headlines.append({"id": f"news:{url}", "published_utc": _iso(published), "title": title,
                              "source": info.get("source_name"), "tone": tone or None})
        statements = [{"id": f"news:{url}", "published_utc": _iso(published), "source": source, "title": title,
                       "summary": (summary or "")[:400] or None} for published, source, title, url, summary in banks]
        status = "READY" if headlines or statements else "UNAVAILABLE"
        return {"status": status, "recipe": NEWS_RECIPE, "window_hours": hours, "headlines": headlines,
                "central_bank": statements}

    def macro(self, at: datetime, observations: int = 3) -> dict:
        t = _naive_utc(at)
        rows = self.con.execute(f"""
            WITH visible AS (
                SELECT * FROM read_parquet('{self.root}/macro_observations.parquet')
                WHERE realtime_start < DATE '{t.date()}'
            ), latest AS (
                SELECT series_id, observation_date, arg_max(value, realtime_start) AS value,
                       max(realtime_start) AS vintage
                FROM visible GROUP BY series_id, observation_date
            ), ranked AS (
                SELECT *, row_number() OVER (PARTITION BY series_id ORDER BY observation_date DESC) AS n
                FROM latest WHERE value <> '.'
            )
            SELECT series_id, observation_date, value, vintage FROM ranked
            WHERE n <= {int(observations)} ORDER BY series_id, observation_date
        """).fetchall()
        series: dict[str, list] = {}
        for series_id, observed, value, vintage in rows:
            series.setdefault(series_id, []).append(
                {"date": observed.isoformat(), "value": value, "vintage": vintage.isoformat()})
        missing = [s for s in MACRO_SERIES if s not in series]
        return {"status": "READY" if series else "UNAVAILABLE", "series": series, "missing": missing,
                "visibility": "a vintage is visible from the UTC day after its realtime_start"}

    def calendar(self, at: datetime, days_back: int = 3, days_ahead: int = 7) -> dict:
        t = _naive_utc(at)
        rows = self.con.execute(f"""
            SELECT DISTINCT release_id, release_date FROM read_parquet('{self.root}/macro_release_dates.parquet')
            WHERE release_id IN {tuple(EVENT_RELEASES)}
              AND release_date BETWEEN DATE '{(t - timedelta(days=days_back)).date()}'
                                   AND DATE '{(t + timedelta(days=days_ahead)).date()}'
            ORDER BY release_date, release_id
        """).fetchall()
        today = t.date()
        events = [{"release": EVENT_RELEASES[release_id], "date": day.isoformat(),
                   "when": "past" if day < today else "today, time unknown" if day == today else "upcoming"}
                  for release_id, day in rows]
        return {"events": events, "basis": "schedule as captured; reschedules after the decision time may show"}


def replay_context(symbol: str, at: datetime, ticks, news: NewsArchive) -> dict:
    """Everything visible at `at` for one instrument, with the assumptions behind it."""
    sentiment_start = datetime(2026, 10, 9, tzinfo=timezone.utc)
    return {
        "symbol": symbol,
        "decision_at_utc": at.astimezone(timezone.utc).isoformat(),
        "market": ticks.context(symbol, at),
        "news": news.news(symbol, at),
        "macro": news.macro(at),
        "calendar": news.calendar(at),
        "sentiment": {"status": "UNAVAILABLE",
                      "reason": "not captured before 2026-10-09" if at < sentiment_start
                      else "not yet in the replay snapshot"},
        "assumptions": [
            "replay over backfilled data: a retrospective simulation, not live performance",
            "exported ticks are visible at their event time",
            "backfilled GDELT items are visible 15 minutes after their batch time",
            "macro vintages are visible from the UTC day after their realtime_start",
        ],
    }
