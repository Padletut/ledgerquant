"""Append-only news items and their fetch log.

Revision ID: 0006_news
Revises: 0005_shadow_decisions
"""

from alembic import op

from ledgerquant.news.storage import fetches, items


revision = "0006_news"
down_revision = "0005_shadow_decisions"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SCHEMA news")
    fetches.create(op.get_bind(), checkfirst=False)
    items.create(op.get_bind(), checkfirst=False)
    op.execute("CREATE INDEX news_fetch_url ON news.fetches (url)")
    op.execute("CREATE INDEX news_item_published ON news.items (published_at)")
    op.execute("CREATE INDEX news_item_available ON news.items (available_at) WHERE available_at IS NOT NULL")
    op.execute("""
        CREATE FUNCTION news.reject_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'news records are append-only'; END $$
    """)
    for name in ("fetches", "items"):
        op.execute(f"CREATE TRIGGER no_mutation BEFORE UPDATE OR DELETE ON news.{name} "
                   "FOR EACH ROW EXECUTE FUNCTION news.reject_mutation()")
        op.execute(f"CREATE TRIGGER no_truncate BEFORE TRUNCATE ON news.{name} "
                   "FOR EACH STATEMENT EXECUTE FUNCTION news.reject_mutation()")


def downgrade():
    op.execute("DROP SCHEMA news CASCADE")
