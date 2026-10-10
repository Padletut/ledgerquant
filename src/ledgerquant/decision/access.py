"""Least-privilege database access for the shadow Executor."""

from pathlib import Path

from psycopg import sql


SHADOW_ROLE = "ledgerquant_shadow_worker"


def provision_shadow_worker(engine, password_file: Path) -> None:
    password = password_file.read_text().strip()
    if len(password) < 32:
        raise ValueError("shadow worker credential must contain at least 32 characters")
    with engine.begin() as connection:
        db = connection.connection.driver_connection
        with db.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (SHADOW_ROLE,))
            if cursor.fetchone() is None:
                cursor.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(SHADOW_ROLE)))
            cursor.execute(sql.SQL("ALTER ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD {}")
                           .format(sql.Identifier(SHADOW_ROLE), sql.Literal(password)))
            for schema in ("market", "decision"):
                cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}")
                               .format(sql.Identifier(schema), sql.Identifier(SHADOW_ROLE)))
            for schema, table in (("market", "capture_feed_bindings"),
                                  ("market", "capture_observations"),
                                  ("decision", "shadow_opportunities"),
                                  ("decision", "shadow_events")):
                cursor.execute(sql.SQL("GRANT SELECT ON {}.{} TO {}")
                               .format(sql.Identifier(schema), sql.Identifier(table), sql.Identifier(SHADOW_ROLE)))
            for table in ("shadow_opportunities", "shadow_events"):
                cursor.execute(sql.SQL("GRANT INSERT ON decision.{} TO {}")
                               .format(sql.Identifier(table), sql.Identifier(SHADOW_ROLE)))
