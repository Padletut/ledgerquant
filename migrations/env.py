"""Alembic environment for market capture and bounded research schemas."""

from alembic import context
from sqlalchemy import create_engine

from ledgerquant.capture.settings import database_url_from_environment
from ledgerquant.capture.storage import metadata
from ledgerquant.research.tables import metadata as research_metadata


target_metadata = [metadata, research_metadata]


def run_migrations_online() -> None:
    engine = create_engine(database_url_from_environment(), pool_pre_ping=True)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations_online()
