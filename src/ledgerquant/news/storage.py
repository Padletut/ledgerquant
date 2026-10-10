"""Append-only news items, macro calendar and vintages, and the fetch log that proves when each was obtained.

`first_seen_at` is when LedgerQuant first had an item. For live fetches it is also
`available_at`. Backfilled items keep `available_at` empty: downloading an old
batch now does not show when it could first have been read.

Macro release dates and ALFRED observation vintages carry the source's own dates
(release date, vintage date) plus `first_seen_at`.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, MetaData, String, Table, Text,
    UniqueConstraint, and_, create_engine, select,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID, insert
from sqlalchemy.engine import Engine

from ledgerquant.news.sources import NewsItem, Observation, ReleaseDate

metadata = MetaData(schema="news")
fetches = Table(
    "fetches", metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("source", String(40), nullable=False),
    Column("url", Text, nullable=False),
    Column("backfill", Boolean, nullable=False),
    Column("requested_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True), nullable=False),
    Column("http_status", Integer),
    Column("error", String(300)),
    Column("bytes", Integer, nullable=False),
    Column("sha256", String(64)),
    Column("records", Integer, nullable=False),
    Column("items_parsed", Integer, nullable=False),
    Column("items_inserted", Integer, nullable=False),
)
items = Table(
    "items", metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("source", String(40), nullable=False),
    Column("source_item_id", String(300), nullable=False),
    Column("url", Text, nullable=False),
    Column("title", Text, nullable=False),
    Column("summary", Text),
    Column("published_at", DateTime(timezone=True)),
    Column("first_seen_at", DateTime(timezone=True), nullable=False),
    Column("available_at", DateTime(timezone=True)),
    Column("backfilled", Boolean, nullable=False),
    Column("fetch_id", UUID(as_uuid=True),
           ForeignKey("news.fetches.id", deferrable=True, initially="DEFERRED"), nullable=False),
    Column("filter_version", String(40)),
    Column("details", JSONB, nullable=False),
    UniqueConstraint("source", "source_item_id", name="uq_news_source_item"),
    CheckConstraint("(backfilled AND available_at IS NULL) OR "
                    "(NOT backfilled AND available_at = first_seen_at)", name="ck_news_availability"),
)
release_dates = Table(
    "macro_release_dates", metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("release_id", Integer, nullable=False),
    Column("release_name", Text, nullable=False),
    Column("release_date", Date, nullable=False),
    Column("first_seen_at", DateTime(timezone=True), nullable=False),
    Column("fetch_id", UUID(as_uuid=True),
           ForeignKey("news.fetches.id", deferrable=True, initially="DEFERRED"), nullable=False),
    UniqueConstraint("release_id", "release_date", name="uq_macro_release_date"),
)
observations = Table(
    "macro_observations", metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("series_id", String(64), nullable=False),
    Column("observation_date", Date, nullable=False),
    Column("realtime_start", Date, nullable=False),
    Column("value", String(40), nullable=False),
    Column("first_seen_at", DateTime(timezone=True), nullable=False),
    Column("fetch_id", UUID(as_uuid=True),
           ForeignKey("news.fetches.id", deferrable=True, initially="DEFERRED"), nullable=False),
    UniqueConstraint("series_id", "observation_date", "realtime_start", name="uq_macro_observation_vintage"),
)


class NewsStore:
    def __init__(self, engine: Engine):
        self.engine = engine

    def fetched(self, url: str) -> bool:
        """True when a URL was already fetched successfully or confirmed missing (404)."""
        query = select(fetches.c.id).where(and_(
            fetches.c.url == url, fetches.c.error.is_(None), fetches.c.http_status.in_((200, 404)))).limit(1)
        with self.engine.connect() as connection:
            return connection.execute(query).first() is not None

    def record(self, *, source: str, url: str, backfill: bool, requested_at: datetime,
               completed_at: datetime, http_status: int | None, error: str | None, size: int,
               sha256: str | None, records: int, parsed: list) -> int:
        """Store one fetch and what it yielded; already known records are not duplicated."""
        fetch_id = uuid.uuid4()
        news = [p for p in parsed if isinstance(p, NewsItem)]
        dates = [p for p in parsed if isinstance(p, ReleaseDate)]
        vintages = [p for p in parsed if isinstance(p, Observation)]
        if len(news) + len(dates) + len(vintages) != len(parsed):
            raise TypeError("unsupported parsed record")
        batches = []
        if news:
            batches.append((items, "uq_news_source_item", [{
                "id": uuid.uuid4(), "source": item.source, "source_item_id": item.source_item_id,
                "url": item.url, "title": item.title, "summary": item.summary,
                "published_at": item.published_at, "first_seen_at": completed_at,
                "available_at": None if backfill else completed_at, "backfilled": backfill,
                "fetch_id": fetch_id, "filter_version": item.filter_version, "details": item.details,
            } for item in news]))
        if dates:
            batches.append((release_dates, "uq_macro_release_date", [{
                "id": uuid.uuid4(), "release_id": d.release_id, "release_name": d.release_name,
                "release_date": d.release_date, "first_seen_at": completed_at, "fetch_id": fetch_id,
            } for d in dates]))
        if vintages:
            batches.append((observations, "uq_macro_observation_vintage", [{
                "id": uuid.uuid4(), "series_id": o.series_id, "observation_date": o.observation_date,
                "realtime_start": o.realtime_start, "value": o.value, "first_seen_at": completed_at,
                "fetch_id": fetch_id,
            } for o in vintages]))
        with self.engine.begin() as connection:
            inserted = 0
            for table, constraint, rows in batches:
                # The foreign key is deferred, so the fetch row is written once with the final count.
                for offset in range(0, len(rows), 1000):
                    result = connection.execute(
                        insert(table).values(rows[offset:offset + 1000])
                        .on_conflict_do_nothing(constraint=constraint).returning(table.c.id))
                    inserted += len(result.fetchall())
            connection.execute(insert(fetches).values(
                id=fetch_id, source=source, url=url, backfill=backfill, requested_at=requested_at,
                completed_at=completed_at, http_status=http_status, error=error, bytes=size,
                sha256=sha256, records=records, items_parsed=len(parsed), items_inserted=inserted))
            return inserted


def create_store(url) -> NewsStore:
    return NewsStore(create_engine(url, pool_pre_ping=True))
