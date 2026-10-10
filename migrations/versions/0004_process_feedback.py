"""Add operator-owned process assessments and derived research feedback.

Revision ID: 0004_process_feedback
Revises: 0003_research_registry
"""

from alembic import op

from ledgerquant.research.tables import FEEDBACK_TABLES


revision = "0004_process_feedback"
down_revision = "0003_research_registry"
branch_labels = None
depends_on = None


def upgrade():
    # A fresh database may already hold these tables from 0003's create_all;
    # creation is therefore conditional and the append-only triggers are replaced.
    for table in FEEDBACK_TABLES:
        table.create(op.get_bind(), checkfirst=True)
        op.execute(f"CREATE OR REPLACE TRIGGER no_mutation BEFORE UPDATE OR DELETE ON research.{table.name} "
                   "FOR EACH ROW EXECUTE FUNCTION research.reject_mutation()")
        op.execute(f"CREATE OR REPLACE TRIGGER no_truncate BEFORE TRUNCATE ON research.{table.name} "
                   "FOR EACH STATEMENT EXECUTE FUNCTION research.reject_mutation()")


def downgrade():
    for table in reversed(FEEDBACK_TABLES):
        table.drop(op.get_bind(), checkfirst=True)
