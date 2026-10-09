"""Operator provisioning of a worker with no evidence or capture write rights."""

from pathlib import Path

from psycopg import sql

from .tables import WORKER_WRITES


WORKER_ROLE = "ledgerquant_research_worker"


def provision_worker(engine, password_file: Path):
    password = password_file.read_text().strip()
    if len(password) < 32:
        raise ValueError("worker credential must contain at least 32 characters")
    # Identifiers and password are quoted by psycopg, never logged or passed
    # through shell arguments. Re-provisioning explicitly rotates the password.
    with engine.begin() as connection:
        db = connection.connection.driver_connection
        with db.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (WORKER_ROLE,))
            if cursor.fetchone() is None:
                cursor.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(WORKER_ROLE)))
            cursor.execute(sql.SQL("ALTER ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD {}")
                           .format(sql.Identifier(WORKER_ROLE), sql.Literal(password)))
            cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA research TO {}").format(sql.Identifier(WORKER_ROLE)))
            cursor.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA research TO {}").format(sql.Identifier(WORKER_ROLE)))
            for table in WORKER_WRITES:
                cursor.execute(sql.SQL("GRANT INSERT ON research.{} TO {}")
                               .format(sql.Identifier(table.name), sql.Identifier(WORKER_ROLE)))
            # SELECT FOR UPDATE needs an UPDATE privilege; immutable triggers
            # still reject actual changes to this identity column.
            cursor.execute(sql.SQL("GRANT UPDATE (id) ON research.campaigns TO {}").format(sql.Identifier(WORKER_ROLE)))
