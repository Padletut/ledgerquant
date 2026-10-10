"""Append-only scheduled opportunities and shadow Executor events.

Revision ID: 0005_shadow_decisions
Revises: 0004_process_feedback
"""

from alembic import op


revision = "0005_shadow_decisions"
down_revision = "0004_process_feedback"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SCHEMA decision")
    op.execute("""
        CREATE TABLE decision.shadow_opportunities (
            id uuid PRIMARY KEY,
            feed_id varchar(100) NOT NULL REFERENCES market.capture_feed_bindings(feed_id),
            symbol varchar(64) NOT NULL,
            scheduled_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL,
            config jsonb NOT NULL,
            config_sha256 char(64) NOT NULL,
            UNIQUE (feed_id, symbol, scheduled_at)
        )
    """)
    op.execute("""
        CREATE TABLE decision.shadow_events (
            id uuid PRIMARY KEY,
            opportunity_id uuid NOT NULL REFERENCES decision.shadow_opportunities(id),
            phase varchar(10) NOT NULL CHECK (phase IN ('STARTED', 'FINAL')),
            occurred_at timestamptz NOT NULL,
            payload jsonb NOT NULL,
            payload_sha256 char(64) NOT NULL,
            UNIQUE (opportunity_id, phase)
        )
    """)
    op.execute("CREATE INDEX shadow_opportunity_time ON decision.shadow_opportunities (scheduled_at)")
    op.execute("""
        CREATE FUNCTION decision.reject_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'shadow records are append-only'; END $$
    """)
    for name in ("shadow_opportunities", "shadow_events"):
        op.execute(f"CREATE TRIGGER no_mutation BEFORE UPDATE OR DELETE ON decision.{name} "
                   "FOR EACH ROW EXECUTE FUNCTION decision.reject_mutation()")
        op.execute(f"CREATE TRIGGER no_truncate BEFORE TRUNCATE ON decision.{name} "
                   "FOR EACH STATEMENT EXECUTE FUNCTION decision.reject_mutation()")


def downgrade():
    op.execute("DROP SCHEMA decision CASCADE")
