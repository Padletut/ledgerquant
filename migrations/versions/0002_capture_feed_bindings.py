"""Bind each feed ID to one broker source identity.

Revision ID: 0002_capture_feed_bindings
Revises: 0001_capture_observations
"""

from alembic import op

from ledgerquant.capture.storage import feed_bindings


revision = "0002_capture_feed_bindings"
down_revision = "0001_capture_observations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    feed_bindings.create(op.get_bind(), checkfirst=False)
    op.execute(
        "CREATE TRIGGER capture_binding_no_update_delete "
        "BEFORE UPDATE OR DELETE ON market.capture_feed_bindings "
        "FOR EACH ROW EXECUTE FUNCTION market.reject_capture_mutation()"
    )
    op.execute(
        "CREATE TRIGGER capture_binding_no_truncate "
        "BEFORE TRUNCATE ON market.capture_feed_bindings "
        "FOR EACH STATEMENT EXECUTE FUNCTION market.reject_capture_mutation()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER capture_binding_no_truncate ON market.capture_feed_bindings")
    op.execute("DROP TRIGGER capture_binding_no_update_delete ON market.capture_feed_bindings")
    feed_bindings.drop(op.get_bind(), checkfirst=False)
