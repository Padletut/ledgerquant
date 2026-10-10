"""Requires a disposable migrated PostgreSQL database, never the capture database."""

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError

from ledgerquant.agents.definitions import CampaignPolicy
from ledgerquant.agents.tools import ResearchTools
from ledgerquant.models.generation import ModelProfile
from ledgerquant.research import tables as t
from ledgerquant.research.bootstrap import bootstrap, invalidate_evidence
from ledgerquant.research.imports import load_legacy_bundle
from tests.private_evidence import private_evidence_root
from ledgerquant.research.registry import BudgetExceeded, Registry, RegistryError
from tests.unit.test_agent_catalog import proposal_payload
from tests.unit.test_requirement_scope import scoped_proposal


@pytest.fixture
def registered():
    url = os.getenv("RESEARCH_TEST_DATABASE_URL")
    if not url:
        pytest.skip("disposable PostgreSQL URL required")
    engine = create_engine(url)
    assert engine.url.database == "research_test", "refusing non-test database"
    # Each test starts with a fresh ledger. Trigger bypass exists only in this
    # explicitly disposable test fixture, using its owner credential.
    with engine.begin() as c:
        for table in t.metadata.sorted_tables:
            c.execute(text(f"ALTER TABLE research.{table.name} DISABLE TRIGGER USER"))
        c.execute(text("TRUNCATE research.artifacts CASCADE"))
        for table in t.metadata.sorted_tables:
            c.execute(text(f"ALTER TABLE research.{table.name} ENABLE TRIGGER USER"))
    registry = Registry(engine)
    profile = ModelProfile(provider="fixture", endpoint="http://127.0.0.1", model="scripted-test",
                           max_output_tokens=512, max_request_bytes=40000, timeout_seconds=10,
                           max_steps_per_agent=4, input_usd_per_million=0, output_usd_per_million=0,
                           max_run_usd=1, price_basis="test fixture", knowledge_exposure="test fixture")
    bundle = load_legacy_bundle(private_evidence_root())
    policy = CampaignPolicy(max_runs=2, max_invocations=2, max_reserved_tokens=8000, max_usd=1)
    config = bootstrap(registry, bundle, profile, policy, "test-" + uuid4().hex)
    yield registry, config, profile
    engine.dispose()


def start(registry, config, command=None):
    return registry.start_run(command or uuid4().hex, config["campaign_id"], config["snapshot_id"],
                              config["versions"]["research"], config["versions"]["critic"], {"kind": "test_fixture"})


def test_import_idempotency_and_original_evidence(registered):
    registry, config, _ = registered
    with registry.engine.connect() as c:
        assert len(c.execute(select(t.evidence)).all()) == 2
        assert {r.state for r in c.execute(select(t.windows))} == {"CONSUMED"}
    original = registry.read(registry.get(t.evidence, "eurusd_four_hour_direction_2021_replication_v1")["artifact_id"])
    assert original["related_trial_count"] == 1
    assert original["gate_decision"] == "TEMPORAL_FAILED"


def test_concurrent_run_reservation_and_idempotent_delivery(registered):
    registry, config, _ = registered
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda _: start(registry, config, "same-" + config["campaign_id"]), range(4)))
    assert sum(created for _, created in results) == 1
    assert len({run["id"] for run, _ in results}) == 1
    start(registry, config)
    with pytest.raises(BudgetExceeded):
        start(registry, config)


def test_unknown_invocation_reserves_budget_even_without_response(registered):
    registry, config, _ = registered
    run, _ = start(registry, config)
    registry.reserve_invocation(run["id"], config["versions"]["research"], 0, {"test": True})
    with pytest.raises(BudgetExceeded):
        registry.reserve_invocation(run["id"], config["versions"]["research"], 1, {"test": True})


def test_append_only_and_changed_command_rejected(registered):
    registry, config, _ = registered
    run, _ = start(registry, config, "immutable-" + config["campaign_id"])
    with pytest.raises(RegistryError):
        registry.start_run(run["command_key"], config["campaign_id"], config["snapshot_id"],
                           config["versions"]["research"], config["versions"]["critic"], {"changed": True})
    with pytest.raises(DBAPIError):
        with registry.engine.begin() as c:
            c.execute(text("UPDATE research.runs SET command_key='changed' WHERE id=:id"), {"id": run["id"]})


def test_role_denial_does_not_write_draft_and_reads_are_required(registered):
    registry, config, _ = registered
    run, _ = start(registry, config)
    call = registry.reserve_invocation(run["id"], config["versions"]["research"], 0, {})
    critic = ResearchTools(registry, run["id"], "critic")
    with pytest.raises(RegistryError, match="TOOL_CALLER_MISMATCH"):
        critic.execute(call["id"], "submit_hypothesis_draft", proposal_payload())
    research = ResearchTools(registry, run["id"], "research")
    assert research.execute(call["id"], "submit_hypothesis_draft", proposal_payload())["error"] == "REQUIRED_EVIDENCE_NOT_READ"
    assert research.execute(call["id"], "read_source_coverage", {"path": "/etc/passwd"})["error"] == "INVALID_ARGUMENT"
    for name in ("read_source_coverage", "read_released_evidence", "read_development_snapshot"):
        assert "error" not in research.execute(call["id"], name, {})
    assert research.execute(call["id"], "submit_hypothesis_draft", proposal_payload())["status"] == "PROPOSED"


def test_current_cost_field_can_be_corrected_before_draft_is_recorded(registered):
    registry, _, profile = registered
    config = bootstrap(registry, load_legacy_bundle(private_evidence_root()), profile,
        CampaignPolicy(max_runs=1, max_invocations=2, max_reserved_tokens=8000, max_usd=1),
        "field-correction-" + uuid4().hex, contract_version=2)
    run, _ = start(registry, config)
    call = registry.reserve_invocation(run["id"], config["versions"]["research"], 0, {})
    research = ResearchTools(registry, run["id"], "research")
    for name in ("read_source_coverage", "read_released_evidence", "read_development_snapshot"):
        assert "error" not in research.execute(call["id"], name, {})
    first = research.execute(call["id"], "submit_hypothesis_draft", scoped_proposal("current_diagnostic"))
    assert first["error"] == "REQUIREMENT_CONTRADICTION"
    assert research.submitted is False
    with registry.engine.connect() as connection:
        assert connection.execute(select(t.drafts.c.id).where(t.drafts.c.run_id == run["id"])).scalar_one_or_none() is None
    second = research.execute(call["id"], "submit_hypothesis_draft", scoped_proposal("future_economic"))
    assert second["status"] == "PROPOSED"
    assert research.submitted is True
    assert registry.read(registry.get(t.drafts, run["id"])["artifact_id"])["data_requirements"][0]["scope"] == "future_economic"


def test_concurrent_money_reservations_cannot_exceed_campaign(registered):
    registry, _, profile = registered
    charged = profile.model_copy(update={"input_usd_per_million": 10, "output_usd_per_million": 50})
    config = bootstrap(registry, load_legacy_bundle(private_evidence_root()), charged,
        CampaignPolicy(max_runs=2, max_invocations=10, max_reserved_tokens=100000, max_usd=0.10), "money-" + uuid4().hex)
    run, _ = start(registry, config)
    def reserve(step):
        try:
            registry.reserve_invocation(run["id"], config["versions"]["research"], step, {})
            return True
        except BudgetExceeded:
            return False
    with ThreadPoolExecutor(4) as pool:
        assert sum(pool.map(reserve, range(4))) == 1


def test_draft_and_tool_audit_commit_atomically(registered, monkeypatch):
    registry, config, _ = registered
    run, _ = start(registry, config)
    call = registry.reserve_invocation(run["id"], config["versions"]["research"], 0, {})
    tools = ResearchTools(registry, run["id"], "research")
    for name in ("read_source_coverage", "read_released_evidence", "read_development_snapshot"):
        tools.execute(call["id"], name, {})
    def interrupted(*args, **kwargs):
        raise RuntimeError("simulated storage interruption")
    monkeypatch.setattr(registry, "record_tool", interrupted)
    with pytest.raises(RuntimeError):
        tools.execute(call["id"], "submit_hypothesis_draft", proposal_payload())
    with pytest.raises(RegistryError, match="unknown drafts"):
        registry.get(t.drafts, run["id"])
