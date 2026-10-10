"""Retired: bounded research registry.

Revision ID: 0003_research_registry
Revises: 0002_capture_feed_bindings

Retired with the research-governance track (tag archive/research-governance-v1).
The revision ID stays in the chain so existing databases keep their history. A
fresh database creates nothing here; an existing database keeps its ``research``
schema and records untouched until an operator removes them after a backup.
"""


revision = "0003_research_registry"
down_revision = "0002_capture_feed_bindings"
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
