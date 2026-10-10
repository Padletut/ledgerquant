"""Append-only FRED release calendar and ALFRED observation vintages.

Revision ID: 0007_macro
Revises: 0006_news
"""

from alembic import op

from ledgerquant.news.storage import observations, release_dates


revision = "0007_macro"
down_revision = "0006_news"
branch_labels = None
depends_on = None


def upgrade():
    release_dates.create(op.get_bind(), checkfirst=False)
    observations.create(op.get_bind(), checkfirst=False)
    op.execute("CREATE INDEX macro_release_on ON news.macro_release_dates (release_date)")
    op.execute("CREATE INDEX macro_observation_series ON news.macro_observations (series_id, realtime_start)")
    for name in ("macro_release_dates", "macro_observations"):
        op.execute(f"CREATE TRIGGER no_mutation BEFORE UPDATE OR DELETE ON news.{name} "
                   "FOR EACH ROW EXECUTE FUNCTION news.reject_mutation()")
        op.execute(f"CREATE TRIGGER no_truncate BEFORE TRUNCATE ON news.{name} "
                   "FOR EACH STATEMENT EXECUTE FUNCTION news.reject_mutation()")


def downgrade():
    op.execute("DROP TABLE news.macro_observations")
    op.execute("DROP TABLE news.macro_release_dates")
