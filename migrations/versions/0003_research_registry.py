"""Add the bounded research registry, preserving the capture schema.

Revision ID: 0003_research_registry
Revises: 0002_capture_feed_bindings
"""

from alembic import op

from ledgerquant.research.tables import metadata


revision = "0003_research_registry"
down_revision = "0002_capture_feed_bindings"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SCHEMA research")
    metadata.create_all(op.get_bind(), checkfirst=False)
    op.execute("""
        CREATE FUNCTION research.reject_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'research records are append-only'; END $$
    """)
    for table in metadata.sorted_tables:
        op.execute(f"CREATE TRIGGER no_mutation BEFORE UPDATE OR DELETE ON research.{table.name} "
                   "FOR EACH ROW EXECUTE FUNCTION research.reject_mutation()")
        op.execute(f"CREATE TRIGGER no_truncate BEFORE TRUNCATE ON research.{table.name} "
                   "FOR EACH STATEMENT EXECUTE FUNCTION research.reject_mutation()")


def downgrade():
    metadata.drop_all(op.get_bind(), checkfirst=False)
    op.execute("DROP FUNCTION research.reject_mutation()")
    op.execute("DROP SCHEMA research")
