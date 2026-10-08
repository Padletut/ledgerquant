"""Transactional, idempotent writes to the append-only capture table."""

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    MetaData,
    Numeric,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, insert
from sqlalchemy.engine import Engine

from ledgerquant.capture.contracts import CaptureBatch


metadata = MetaData(schema="market")
feed_bindings = Table(
    "capture_feed_bindings",
    metadata,
    Column("feed_id", String(100), primary_key=True),
    Column("source", String(30), nullable=False),
    Column("broker", String(120), nullable=False),
    Column("environment", String(10), nullable=False),
    Column("account_id", String(40), nullable=False),
    Column("symbol", String(64), nullable=False),
    Column("first_ingested_at", DateTime(timezone=True), nullable=False),
)
observations = Table(
    "capture_observations",
    metadata,
    Column("message_id", UUID(as_uuid=True), primary_key=True),
    Column("feed_id", String(100), nullable=False),
    Column("session_id", UUID(as_uuid=True), nullable=False),
    Column("sequence", BigInteger, nullable=False),
    Column("source", String(30), nullable=False),
    Column("broker", String(120), nullable=False),
    Column("environment", String(10), nullable=False),
    Column("account_id", String(40), nullable=False),
    Column("symbol", String(64), nullable=False),
    Column("kind", String(20), nullable=False),
    Column("event_at", DateTime(timezone=True)),
    Column("observed_at", DateTime(timezone=True), nullable=False),
    Column("sent_at", DateTime(timezone=True), nullable=False),
    Column("received_at", DateTime(timezone=True), nullable=False),
    Column("ingested_at", DateTime(timezone=True), nullable=False),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("bid", Numeric(20, 10)),
    Column("ask", Numeric(20, 10)),
    Column("buy_percentage", Numeric(9, 6)),
    Column("sell_percentage", Numeric(9, 6)),
    Column("sentiment_trigger", String(10)),
    Column("quality_flag", String(20), nullable=False),
    Column("cbot_version", String(40), nullable=False),
    Column("payload_sha256", String(64), nullable=False),
    UniqueConstraint("feed_id", "session_id", "sequence", name="uq_capture_sequence"),
    CheckConstraint("sequence > 0", name="ck_capture_sequence_positive"),
    CheckConstraint(
        "(kind = 'tick' AND event_at IS NOT NULL AND bid > 0 AND ask >= bid "
        "AND buy_percentage IS NULL AND sell_percentage IS NULL AND sentiment_trigger IS NULL) "
        "OR (kind = 'sentiment' AND event_at IS NULL AND bid IS NULL AND ask IS NULL "
        "AND buy_percentage BETWEEN 0 AND 100 AND sell_percentage BETWEEN 0 AND 100 "
        "AND sentiment_trigger IN ('startup', 'update'))",
        name="ck_capture_kind_payload",
    ),
    CheckConstraint(
        "quality_flag IN ('OBSERVED', 'ZERO_AMBIGUOUS')",
        name="ck_capture_quality_flag",
    ),
)


class CaptureConflict(Exception):
    """A stable observation identity was reused with different content."""


class CaptureStore:
    def __init__(self, engine: Engine):
        self.engine = engine

    def ping(self) -> None:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    def append(self, batch: CaptureBatch, received_at: datetime) -> tuple[int, int]:
        ingested_at = datetime.now(timezone.utc)
        rows = []
        for item in batch.observations:
            payload = item.model_dump(mode="json")
            digest = hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            rows.append(
                {
                    **item.model_dump(exclude={"message_id"}),
                    "message_id": item.message_id,
                    "sent_at": batch.sent_at,
                    "received_at": received_at,
                    "ingested_at": ingested_at,
                    "available_at": ingested_at,
                    "quality_flag": item.quality_flag,
                    "payload_sha256": digest,
                }
            )

        with self.engine.begin() as connection:
            first = batch.observations[0]
            identity = {
                "source": first.source,
                "broker": first.broker,
                "environment": first.environment,
                "account_id": first.account_id,
                "symbol": first.symbol,
            }
            connection.execute(
                insert(feed_bindings)
                .values(feed_id=first.feed_id, first_ingested_at=ingested_at, **identity)
                .on_conflict_do_nothing()
            )
            binding = connection.execute(
                select(feed_bindings).where(feed_bindings.c.feed_id == first.feed_id).with_for_update()
            ).one()._mapping
            if any(binding[key] != value for key, value in identity.items()):
                raise CaptureConflict("feed ID belongs to another source identity")
            statement = (
                insert(observations)
                .values(rows)
                .on_conflict_do_nothing()
                .returning(observations.c.message_id)
            )
            inserted = len(connection.execute(statement).scalars().all())
            stored = dict(
                connection.execute(
                    select(observations.c.message_id, observations.c.payload_sha256).where(
                        observations.c.message_id.in_([item.message_id for item in batch.observations])
                    )
                ).all()
            )
            if len(stored) != len(rows) or any(
                stored.get(row["message_id"]) != row["payload_sha256"] for row in rows
            ):
                raise CaptureConflict("message ID or source sequence conflicts with stored data")
        return inserted, len(rows) - inserted


def create_store(database_url) -> CaptureStore:
    return CaptureStore(create_engine(database_url, pool_pre_ping=True))
