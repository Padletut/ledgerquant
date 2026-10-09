"""Real database permission and irreversible-ledger checks."""

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError

from ledgerquant.research import tables as t
from ledgerquant.research.access import provision_worker, WORKER_ROLE
from ledgerquant.research.registry import Registry
from tests.integration.test_research_registry import registered, start


def test_worker_cannot_forge_evidence_freezes_or_capture_rows(registered, tmp_path):
    registry, config, _ = registered
    password = "disposable-research-test-" + uuid4().hex
    secret = tmp_path / "worker.pwd"
    secret.write_text(password)
    provision_worker(registry.engine, secret)
    engine = create_engine(registry.engine.url.set(username=WORKER_ROLE, password=password))
    try:
        worker = Registry(engine)
        run, _ = start(worker, config)
        worker.reserve_invocation(run["id"], config["versions"]["research"], 0, {})
        for sql in (
            "INSERT INTO research.evidence (id) VALUES ('forged')",
            "INSERT INTO research.commitments (id) VALUES ('forged')",
            "UPDATE research.campaigns SET id=id",
            "DELETE FROM research.runs",
            "TRUNCATE research.runs CASCADE",
            "SELECT * FROM market.capture_observations LIMIT 1",
            "INSERT INTO market.capture_observations (observation_id) VALUES ('forged')",
        ):
            with pytest.raises(DBAPIError) as error:
                with engine.begin() as c:
                    c.execute(text(sql))
            assert error.value.orig.sqlstate in {"42501", "P0001"}
    finally:
        engine.dispose()
