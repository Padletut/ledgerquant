"""PostgreSQL owner for prospective shadow opportunities and immutable events."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import text

from ledgerquant.records import canonical, digest


class ShadowStore:
    def __init__(self, engine):
        self.engine = engine

    def schedule(self, feed_id: str, symbol: str, scheduled_at: datetime, config: dict) -> dict:
        if scheduled_at.tzinfo is None or scheduled_at.utcoffset() is None:
            raise ValueError("scheduled_at must include a UTC offset")
        if scheduled_at < datetime.now(timezone.utc):
            raise ValueError("cannot schedule a historical opportunity")
        with self.engine.begin() as connection:
            binding = connection.execute(text("""
                SELECT symbol FROM market.capture_feed_bindings WHERE feed_id = :feed_id
            """), {"feed_id": feed_id}).scalar_one_or_none()
            if binding != symbol:
                raise ValueError("feed and symbol are not bound")
            found = connection.execute(text("""
                INSERT INTO decision.shadow_opportunities
                  (id, feed_id, symbol, scheduled_at, created_at, config, config_sha256)
                VALUES (:id, :feed_id, :symbol, :scheduled_at, :created_at,
                        CAST(:config AS jsonb), :config_sha256)
                ON CONFLICT (feed_id, symbol, scheduled_at) DO NOTHING
                RETURNING id
            """), {"id": uuid4(), "feed_id": feed_id, "symbol": symbol,
                   "scheduled_at": scheduled_at, "created_at": datetime.now(timezone.utc),
                   "config": canonical(config), "config_sha256": digest(config)}).scalar_one_or_none()
            row = connection.execute(text("""
                SELECT id, feed_id, symbol, scheduled_at, config, config_sha256
                FROM decision.shadow_opportunities
                WHERE feed_id = :feed_id AND symbol = :symbol AND scheduled_at = :scheduled_at
            """), {"feed_id": feed_id, "symbol": symbol, "scheduled_at": scheduled_at}).mappings().one()
            if row["config_sha256"] != digest(config):
                raise ValueError("opportunity already exists with different configuration")
            return dict(row)

    def opportunity(self, opportunity_id):
        with self.engine.connect() as connection:
            row = connection.execute(text("""
                SELECT id, feed_id, symbol, scheduled_at, config, config_sha256
                FROM decision.shadow_opportunities WHERE id = :id
            """), {"id": opportunity_id}).mappings().one()
            return dict(row)

    def quotes(self, feed_id: str, symbol: str, cutoff: datetime):
        """One committed quote near now and near each earlier context landmark."""
        query = text("""
            SELECT message_id, symbol, kind, event_at, observed_at, received_at,
                   ingested_at, bid, ask, quality_flag
            FROM market.capture_observations
            WHERE feed_id = :feed_id AND symbol = :symbol AND kind = 'tick'
              AND ingested_at <= :cutoff AND event_at <= :cutoff
              AND event_at <= :cutoff - (:offset * interval '1 minute')
              AND event_at >= :cutoff - (:oldest * interval '1 minute')
            ORDER BY event_at DESC, ingested_at DESC LIMIT 1
        """)
        with self.engine.connect() as connection:
            selected = {}
            for offset, oldest in ((0, 30), (5, 7), (15, 17), (30, 32)):
                row = connection.execute(query, {"feed_id": feed_id, "symbol": symbol,
                    "cutoff": cutoff, "offset": offset, "oldest": oldest}).mappings().one_or_none()
                if row is not None:
                    selected[row["message_id"]] = dict(row)
            return list(selected.values())

    def event(self, opportunity_id, phase: str, payload: dict) -> bool:
        with self.engine.begin() as connection:
            inserted = connection.execute(text("""
                INSERT INTO decision.shadow_events
                  (id, opportunity_id, phase, occurred_at, payload, payload_sha256)
                VALUES (:id, :opportunity_id, :phase, :occurred_at,
                        CAST(:payload AS jsonb), :payload_sha256)
                ON CONFLICT (opportunity_id, phase) DO NOTHING RETURNING id
            """), {"id": uuid4(), "opportunity_id": opportunity_id, "phase": phase,
                   "occurred_at": datetime.now(timezone.utc),
                   "payload": canonical(payload), "payload_sha256": digest(payload)}).scalar_one_or_none()
            return inserted is not None

    def events(self, opportunity_id):
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(text("""
                SELECT phase, occurred_at, payload, payload_sha256
                FROM decision.shadow_events WHERE opportunity_id = :id
                ORDER BY occurred_at, phase
            """), {"id": opportunity_id}).mappings()]
