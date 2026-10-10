"""Poll central-bank feeds, GDELT GKG batches and FRED/ALFRED, and store what LedgerQuant obtained, and when.

Every request is recorded in news.fetches, including failures and missing GDELT
batches (404), so gaps stay visible. A missed GDELT batch is caught up later with
its real fetch time as availability; nothing is back-dated. API keys are sent as
request parameters and never stored in the logged URL.
"""

import hashlib
import json
import os
import re
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree.ElementTree import ParseError

import httpx
from sqlalchemy.exc import SQLAlchemyError

from ledgerquant.news.sources import (
    FRED_SERIES, parse_feed, parse_fred_observations, parse_fred_release, parse_fred_release_dates, parse_gkg,
)

FEEDS = {
    "fed_press": "https://www.federalreserve.gov/feeds/press_all.xml",
    "ecb_press": "https://www.ecb.europa.eu/rss/press.html",
    "boe_news": "https://www.bankofengland.co.uk/rss/news",
}
GDELT_BASE = "https://data.gdeltproject.org/gdeltv2/"
FRED_BASE = "https://api.stlouisfed.org/fred/"
FRED_OBSERVATION_START = "2024-01-01"
FRED_REALTIME_START = "2025-09-01"
GKG_STEP = timedelta(minutes=15)
MAX_BYTES = 64 * 1024 * 1024
USER_AGENT = "LedgerQuant-news/0.1 (research data collection)"


def log(event: str, **fields) -> None:
    print(json.dumps({"event": event, **fields}, default=str), flush=True)


def gkg_url(at: datetime) -> str:
    return f"{GDELT_BASE}{at:%Y%m%d%H%M%S}.gkg.csv.zip"


def gkg_grid(start: datetime, end: datetime) -> list[datetime]:
    """15-minute batch times in [start, end], aligned to the GDELT grid."""
    cursor = start.replace(minute=start.minute - start.minute % 15, second=0, microsecond=0)
    if cursor < start:
        cursor += GKG_STEP
    times = []
    while cursor <= end:
        times.append(cursor)
        cursor += GKG_STEP
    return times


class Collector:
    def __init__(self, store, client: httpx.Client, clock=lambda: datetime.now(timezone.utc)):
        self.store, self.client, self.clock = store, client, clock

    def fetch(self, source: str, url: str, backfill: bool, parse, secret_params: dict | None = None) -> int:
        requested = self.clock()
        status, error, body = None, None, b""
        try:
            # httpx replaces a URL's query when `params` is given, so merge explicitly.
            target = httpx.URL(url).copy_merge_params(secret_params) if secret_params else url
            with self.client.stream("GET", target) as response:
                status = response.status_code
                if status == 200:
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise ValueError("response too large")
                        chunks.append(chunk)
                    body = b"".join(chunks)
        except (httpx.HTTPError, ValueError) as exc:
            # Exception text can contain the full request URL, including secret parameters.
            error = type(exc).__name__
        completed = self.clock()
        records, parsed = 0, []
        if status == 200 and error is None:
            try:
                records, parsed = parse(body)
            except (ValueError, KeyError, TypeError, zipfile.BadZipFile, ParseError) as exc:
                error = f"PARSE_ERROR:{type(exc).__name__}"
        inserted = self.store.record(
            source=source, url=url, backfill=backfill, requested_at=requested, completed_at=completed,
            http_status=status, error=error, size=len(body),
            sha256=hashlib.sha256(body).hexdigest() if body else None, records=records, parsed=parsed)
        log("fetch", source=source, url=url, status=status, error=error, records=records,
            parsed=len(parsed), inserted=inserted)
        return inserted

    def poll_feeds(self) -> None:
        for source, url in FEEDS.items():
            def parse(body, source=source):
                found = parse_feed(source, body)
                return len(found), found
            self.fetch(source, url, False, parse)

    def latest_gkg(self) -> datetime | None:
        try:
            text = self.client.get(GDELT_BASE + "lastupdate.txt").text
        except httpx.HTTPError as exc:
            log("gdelt_lastupdate_failed", error=type(exc).__name__)
            return None
        match = re.search(r"/(\d{14})\.gkg\.csv\.zip", text)
        if not match:
            log("gdelt_lastupdate_unparsed")
            return None
        return datetime.strptime(match.group(1), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)

    def gkg_batches(self, start: datetime, end: datetime, backfill: bool, pause: float = 0.0) -> None:
        for at in gkg_grid(start, end):
            url = gkg_url(at)
            if self.store.fetched(url):
                continue
            self.fetch("gdelt_gkg", url, backfill, parse_gkg)
            if pause:
                time.sleep(pause)

    def poll_fred(self, api_key: str) -> None:
        """Release calendar for the tracked series' releases, and their ALFRED vintages."""
        key = {"api_key": api_key, "file_type": "json"}
        releases: dict[int, str] = {}
        for series in FRED_SERIES:
            def lookup(body, series=series):
                release_id, name = parse_fred_release(body)
                releases[release_id] = name
                return 1, []
            self.fetch("fred_series_release", f"{FRED_BASE}series/release?series_id={series}", False, lookup, key)
        for release_id, name in sorted(releases.items()):
            def dates(body, name=name):
                found = parse_fred_release_dates(name, body)
                return len(found), found
            self.fetch("fred_release_dates",
                       f"{FRED_BASE}release/dates?release_id={release_id}&realtime_start={FRED_REALTIME_START}"
                       "&realtime_end=9999-12-31&include_release_dates_with_no_data=true&sort_order=asc&limit=1000",
                       False, dates, key)
        for series in FRED_SERIES:
            def vintages(body, series=series):
                found = parse_fred_observations(series, body)
                return len(found), found
            self.fetch("fred_observations",
                       f"{FRED_BASE}series/observations?series_id={series}&observation_start={FRED_OBSERVATION_START}"
                       f"&realtime_start={FRED_REALTIME_START}&realtime_end=9999-12-31",
                       False, vintages, key)

    def poll_gdelt(self, catch_up: timedelta) -> None:
        latest = self.latest_gkg()
        if latest is not None:
            self.gkg_batches(latest - catch_up, latest, backfill=False)


def client() -> httpx.Client:
    return httpx.Client(timeout=60, follow_redirects=True, headers={"User-Agent": USER_AGENT})


def main() -> None:
    from ledgerquant.capture.settings import database_url_from_environment
    from ledgerquant.news.storage import create_store

    interval = int(os.environ.get("NEWS_POLL_SECONDS", "300"))
    catch_up = timedelta(hours=int(os.environ.get("NEWS_GDELT_CATCH_UP_HOURS", "6")))
    fred_interval = int(os.environ.get("NEWS_FRED_POLL_SECONDS", "21600"))
    key_file = os.environ.get("FRED_API_KEY_FILE")
    fred_key = Path(key_file).read_text().strip() if key_file and Path(key_file).is_file() else ""
    collector = Collector(create_store(database_url_from_environment()), client())
    log("news_collector_started", interval_seconds=interval, gdelt_catch_up=str(catch_up),
        fred_enabled=bool(fred_key), fred_interval_seconds=fred_interval)
    next_fred = 0.0
    while True:
        try:
            collector.poll_feeds()
            collector.poll_gdelt(catch_up)
            if fred_key and time.monotonic() >= next_fred:
                collector.poll_fred(fred_key)
                next_fred = time.monotonic() + fred_interval
        except SQLAlchemyError as exc:
            log("database_error", error=type(exc).__name__)
        time.sleep(interval)


if __name__ == "__main__":
    main()
