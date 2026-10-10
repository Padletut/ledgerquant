"""Retired: process assessments and research feedback.

Revision ID: 0004_process_feedback
Revises: 0003_research_registry

Retired with the research-governance track (tag archive/research-governance-v1).
The revision ID stays in the chain so existing databases keep their history. A
fresh database creates nothing here; an existing database keeps its ``research``
schema and records untouched until an operator removes them after a backup.
"""


revision = "0004_process_feedback"
down_revision = "0003_research_registry"
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
