"""Create the append-only broker observation capture table.

Revision ID: 0001_capture_observations
Revises:
"""

from alembic import op
from ledgerquant.capture.storage import observations


revision = "0001_capture_observations"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS market")
    observations.create(op.get_bind(), checkfirst=False)
    op.execute(
        "CREATE INDEX ix_capture_feed_observed "
        "ON market.capture_observations (feed_id, observed_at)"
    )
    op.execute(
        "CREATE INDEX ix_capture_feed_event "
        "ON market.capture_observations (feed_id, event_at) WHERE event_at IS NOT NULL"
    )
    op.execute(
        "CREATE FUNCTION market.reject_capture_mutation() RETURNS trigger "
        "LANGUAGE plpgsql AS $$ BEGIN "
        "RAISE EXCEPTION 'capture observations are append-only'; "
        "END; $$"
    )
    op.execute(
        "CREATE TRIGGER capture_no_update_delete "
        "BEFORE UPDATE OR DELETE ON market.capture_observations "
        "FOR EACH ROW EXECUTE FUNCTION market.reject_capture_mutation()"
    )
    op.execute(
        "CREATE TRIGGER capture_no_truncate "
        "BEFORE TRUNCATE ON market.capture_observations "
        "FOR EACH STATEMENT EXECUTE FUNCTION market.reject_capture_mutation()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER capture_no_truncate ON market.capture_observations")
    op.execute("DROP TRIGGER capture_no_update_delete ON market.capture_observations")
    op.execute("DROP FUNCTION market.reject_capture_mutation()")
    observations.drop(op.get_bind(), checkfirst=False)
    op.execute("DROP SCHEMA market")
