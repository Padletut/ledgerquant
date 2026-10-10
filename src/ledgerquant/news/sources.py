"""Parse GDELT GKG batches, RSS/Atom feeds and FRED/ALFRED responses into source records.

Parsing is pure: it never fetches or stores. The GDELT relevance filter is a
capture scope for FX and gold drivers, not a trading rule; its version is stored
with every item so the scope can change without rewriting history.
"""

import csv
import io
import json
import re
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from xml.etree import ElementTree

csv.field_size_limit(sys.maxsize)

GDELT_FILTER_VERSION = "gdelt_fx_gold_v1"
GDELT_THEMES = (
    "ECON_WORLDCURRENCIES", "ECON_CURRENCY", "ECON_INFLATION", "ECON_INTEREST_RATE",
    "ECON_CENTRALBANK", "ECON_STOCKMARKET", "ECON_OILPRICE", "ECON_DEBT",
    "ECON_COST_OF_LIVING", "ECON_TRADE", "EPU_POLICY_MONETARY",
)
GDELT_ORGANIZATIONS = re.compile(
    r"federal reserve|european central bank|bank of england|bank of japan|international monetary fund", re.I)
GDELT_TITLE = re.compile(
    r"\b(gold|bullion|dollar|euro|sterling|pound|inflation|interest rates?|rate (cut|hike)s?|central bank|"
    r"fed|fomc|ecb|boe|cpi|payrolls|jobs report|gdp|treasur(y|ies)|bond yields?|forex|fx|currenc(y|ies)|"
    r"recession|tariffs?)\b", re.I)
GKG_COLUMNS = 27
MAX_TEXT = 2000


@dataclass(frozen=True)
class NewsItem:
    source: str
    source_item_id: str
    url: str
    title: str
    published_at: datetime | None
    summary: str | None = None
    filter_version: str | None = None
    details: dict = field(default_factory=dict)


def _gkg_time(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _page_title(extras: str) -> str:
    match = re.search(r"<PAGE_TITLE>(.*?)</PAGE_TITLE>", extras, re.S)
    return unescape(match.group(1)).strip() if match else ""


def parse_gkg(archive: bytes) -> tuple[int, list[NewsItem]]:
    """Return the number of GKG records and the items inside the capture scope."""
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        names = bundle.namelist()
        if len(names) != 1:
            raise ValueError("GKG archive must contain exactly one file")
        text = bundle.read(names[0]).decode("utf-8", "replace")
    total, items = 0, []
    for row in csv.reader(io.StringIO(text), delimiter="\t", quoting=csv.QUOTE_NONE):
        if not row:
            continue
        total += 1
        if len(row) < GKG_COLUMNS:
            continue
        record_id, date, source_name, url = row[0], row[1], row[3], row[4]
        themes = [t for t in row[7].split(";") if t]
        title = _page_title(row[26])
        matched = sorted({t for t in themes if t.startswith(GDELT_THEMES)})
        organizations = GDELT_ORGANIZATIONS.findall(row[13])
        title_match = bool(GDELT_TITLE.search(title))
        if not (matched or organizations or title_match) or not url.startswith("http"):
            continue
        items.append(NewsItem(
            source="gdelt_gkg", source_item_id=record_id, url=url[:MAX_TEXT], title=title[:MAX_TEXT],
            published_at=_gkg_time(date), filter_version=GDELT_FILTER_VERSION,
            details={
                "source_name": source_name,
                "matched_themes": matched,
                "matched_organizations": sorted({o.lower() for o in organizations}),
                "title_match": title_match,
                "themes": row[7][:MAX_TEXT],
                "organizations": row[13][:MAX_TEXT],
                "tone": row[15],
            },
        ))
    return total, items


def _text(element, *names: str) -> str:
    for name in names:
        found = element.find(name)
        if found is not None:
            return (found.text or found.get("href") or "").strip()
    return ""


def _feed_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def parse_feed(source: str, document: bytes) -> list[NewsItem]:
    """Parse RSS 2.0 items or Atom entries; items without a link are skipped."""
    root = ElementTree.fromstring(document)
    atom = "{http://www.w3.org/2005/Atom}"
    entries = root.findall("./channel/item") or root.findall(f"{atom}entry")
    items = []
    for entry in entries:
        link = _text(entry, "link", f"{atom}link")
        if not link.startswith("http"):
            continue
        summary = _text(entry, "description", f"{atom}summary")
        items.append(NewsItem(
            source=source,
            source_item_id=(_text(entry, "guid", f"{atom}id") or link)[:300],
            url=link[:MAX_TEXT],
            title=unescape(_text(entry, "title", f"{atom}title"))[:MAX_TEXT],
            published_at=_feed_time(_text(entry, "pubDate", f"{atom}published", f"{atom}updated")),
            summary=unescape(summary)[:MAX_TEXT] or None,
            details={"categories": [c.text for c in entry.findall("category") if c.text]},
        ))
    return items


# FRED series that drive USD, EUR, GBP and gold. The release calendar covers the
# releases these series belong to. A changed list gets a new version.
FRED_SERIES_VERSION = "fred_macro_v1"
FRED_SERIES = (
    "CPIAUCSL", "CPILFESL", "PCEPILFE", "PAYEMS", "UNRATE", "ICSA", "RSAFS", "GDPC1",
    "DFEDTARU", "DGS10", "DTWEXBGS", "ECBDFR", "CP0000EZ19M086NEST", "IUDSOIA",
)


@dataclass(frozen=True)
class ReleaseDate:
    release_id: int
    release_name: str
    release_date: date


@dataclass(frozen=True)
class Observation:
    """One ALFRED vintage of one observation; `realtime_start` is the vintage date.

    The source clamps `realtime_start` to the query's start, so the earliest vintage
    in a fetch means "known by then", not "first published then".
    """

    series_id: str
    observation_date: date
    realtime_start: date
    value: str


def _fred_json(document: bytes) -> dict:
    payload = json.loads(document)
    if not isinstance(payload, dict) or "error_message" in payload:
        raise ValueError("FRED returned an error payload")
    return payload


def parse_fred_release(document: bytes) -> tuple[int, str]:
    releases = _fred_json(document).get("releases") or []
    if len(releases) != 1:
        raise ValueError("expected exactly one release for the series")
    return int(releases[0]["id"]), str(releases[0]["name"])


def parse_fred_release_dates(release_name: str, document: bytes) -> list[ReleaseDate]:
    return [ReleaseDate(int(row["release_id"]), release_name, date.fromisoformat(row["date"]))
            for row in _fred_json(document)["release_dates"]]


def parse_fred_observations(series_id: str, document: bytes) -> list[Observation]:
    return [Observation(series_id, date.fromisoformat(row["date"]), date.fromisoformat(row["realtime_start"]),
                        str(row["value"]))
            for row in _fred_json(document)["observations"]]
