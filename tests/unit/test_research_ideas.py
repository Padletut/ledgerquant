from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.pool import StaticPool

from ledgerquant.agents.definitions import definition
from ledgerquant.agents.definitions import CampaignPolicy
from ledgerquant.agents.runtime import Runner
from ledgerquant.agents.tools import schemas
from ledgerquant.models.generation import Generation, ModelProfile, ToolCall
from ledgerquant.research.agent_cli import parser
from ledgerquant.research.ideas import Idea, IdeaCritique, references_allowed
from ledgerquant.research import tables as t
from ledgerquant.research.admission import Admission, admit
from ledgerquant.research.bootstrap import bootstrap
from ledgerquant.research.imports import load_legacy_bundle
from tests.private_evidence import private_evidence_root
from ledgerquant.research.proposals import Critique, Proposal
from ledgerquant.research.registry import Registry, RegistryError, append, artifact, now
from ledgerquant.research.types import canonical, digest
from tests.unit.test_agent_catalog import proposal_payload


def idea_payload():
    return {
        "title": "CFD event response",
        "question": "Does an eligible macro release change the next session's EURUSD direction?",
        "instruments": ["EURUSD"],
        "candidate_information": "Macro release timing and predecision prices.",
        "proposed_decision": "Decide whether to take directional exposure after the release.",
        "proposed_payoff": "Return over the following session, net of credible costs if available.",
        "rationale": "A delayed price response might persist after the first reaction.",
        "falsifier": "No improvement over a predeclared no-action or price-only baseline.",
        "source_refs": ["macro-calendar"],
        "related_draft_ids": [],
        "measurement_gaps": ["No reviewed event-time evaluator exists yet."],
    }


def test_idea_is_not_forced_into_eurusd_evaluator_or_economic_status():
    idea = Idea.model_validate({**idea_payload(), "instruments": ["XAUUSD", "US500"]})
    assert idea.instruments == ("XAUUSD", "US500")
    assert "diagnostic" not in idea.model_dump()
    rough = {key: idea_payload()[key] for key in
             ("title", "question", "instruments", "proposed_decision", "proposed_payoff", "rationale")}
    assert Idea.model_validate(rough).falsifier is None
    assert Idea.model_validate({**idea_payload(), "instruments": ["US 500"]}).instruments == ("US 500",)
    for extra in ({"status": "PROMOTED"}, {"net_expectancy": 0.2}, {"family_id": "new"}):
        with pytest.raises(ValidationError):
            Idea.model_validate({**idea_payload(), **extra})


def test_critique_targets_exact_idea_without_assigning_evidence_or_authority():
    critique = IdeaCritique.model_validate({
        "draft_sha256": "a" * 64,
        "summary": "Event timing and source availability need checking.",
        "concerns": ["Release revisions may alter the event population."],
        "source_refs": [],
    })
    assert critique.concerns
    with pytest.raises(ValidationError):
        IdeaCritique.model_validate({**critique.model_dump(), "admit": True})


def test_exploration_has_separate_tools_and_definition():
    profile = ModelProfile(provider="fixture", endpoint="http://127.0.0.1", model="scripted-test",
        max_output_tokens=512, max_request_bytes=40000, timeout_seconds=10,
        max_steps_per_agent=4, input_usd_per_million=0, output_usd_per_million=0,
        max_run_usd=1, price_basis="test fixture", knowledge_exposure="test fixture")
    research_tools = {tool["name"] for tool in schemas("research", workflow="idea_exploration")}
    critic_tools = {tool["name"] for tool in schemas("critic", workflow="idea_exploration")}
    assert research_tools == {"submit_research_idea"}
    assert critic_tools == {"submit_idea_critique"}
    assert definition("research", profile, workflow="idea_exploration") != definition("research", profile)


def test_citations_must_be_in_the_frozen_task():
    task = {"source_refs": ["macro-calendar"], "related_draft_ids": ["prior-idea"]}
    assert references_allowed(task, ("macro-calendar",), ("prior-idea",))
    linked_task = {"parent_idea_draft_id": "prior-idea"}
    assert references_allowed(linked_task, (), ("prior-idea",))
    assert not references_allowed(linked_task, (), ("invented-parent",))
    assert not references_allowed(task, ("invented",))
    assert not references_allowed(task, (), ("invented-parent",))
    assert not references_allowed({"source_refs": "macro-calendar"}, ("macro-calendar",))


def test_cli_can_register_ideas_without_a_legacy_bundle():
    args = parser().parse_args(["register", "--workflow", "idea_exploration", "--policy", "policy.json",
        "--campaign", "ideas", "--profile", "profile.json"])
    assert args.bundle is None
    assert args.workflow == "idea_exploration"


def test_bounded_idea_run_records_critique_and_cannot_enter_evaluator(monkeypatch):
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
    with engine.begin() as connection:
        connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS research")
    t.metadata.create_all(engine)
    monkeypatch.setattr("ledgerquant.research.registry.insert", sqlite_insert)
    registry = Registry(engine)
    profile = ModelProfile(provider="fixture", endpoint="http://127.0.0.1", model="scripted-test",
        max_output_tokens=512, max_request_bytes=40000, timeout_seconds=10,
        max_steps_per_agent=4, input_usd_per_million=0, output_usd_per_million=0,
        max_run_usd=1, price_basis="test fixture", knowledge_exposure="test fixture")
    config = bootstrap(registry, None, profile,
        CampaignPolicy(max_runs=2, max_invocations=6, max_reserved_tokens=200000, max_usd=1),
        "sqlite-idea", workflow="idea_exploration")
    idea = Idea.model_validate(idea_payload()).model_dump(mode="json")

    class Scripted:
        def __init__(self):
            self.profile = profile
            self.calls = 0

        def prepare(self, instructions, conversation, tools):
            return {"instructions": instructions, "input": conversation, "tools": tools}

        def user_message(self, value):
            return {"role": "user", "content": value}

        def tool_result(self, call_id, result):
            return {"call_id": call_id, "result": result}

        def invoke(self, request):
            self.calls += 1
            if self.calls == 1:
                name, arguments = "capability_probe", {"answer": "LEDGERQUANT"}
            elif self.calls == 2:
                name, arguments = "submit_research_idea", idea
            else:
                name, arguments = "submit_idea_critique", {"draft_sha256": digest(idea),
                    "summary": "Needs event-time source coverage and a reviewed evaluator.",
                    "concerns": ["Data availability is unknown."], "source_refs": []}
            return Generation("COMPLETED", {"fixture": name}, [],
                (ToolCall(str(self.calls), name, canonical(arguments)),), 100, 100)

    provider = Scripted()
    task = {"question": "Explore event response", "source_refs": ["macro-calendar"]}
    report = Runner(registry, provider).run(config, "idea-run", task)
    assert report["events"][-1]["detail"]["status"] == "EXPLORATORY_UNMEASURED"
    assert [entry["kind"] for entry in report["events"]] == ["CAPABILITY_VERIFIED", "IDEA_REVIEW", "FINISHED"]
    run_id = report["run"]["id"]
    draft = registry.get(t.drafts, run_id)
    assert registry.read(draft["artifact_id"])["instruments"] == ["EURUSD"]
    assert registry.get(t.critiques, run_id)["draft_id"] == run_id
    assert report["research_records"]["draft"]["body"]["question"] == idea_payload()["question"]
    assert report["research_records"]["critique"]["body"]["concerns"]
    with pytest.raises(RegistryError, match="EXPLORATORY_IDEA_NOT_EVALUABLE"):
        admit(registry, Admission(draft_id=run_id, draft_sha256=draft["artifact_id"], actor="operator",
            action="ADMIT_DEVELOPMENT", reason="Unsupported evaluator", objection_resolutions={}))
    assert Runner(registry, provider).run(config, "idea-run", task) == report
    assert provider.calls == 3

    revised = {**idea_payload(), "title": "CFD event response after Critic review",
        "rationale": "Test the delayed response only after source timing and revision rules are known.",
        "related_draft_ids": [run_id],
        "measurement_gaps": ["A reviewed event-time evaluator and source audit are still needed."]}
    idea = Idea.model_validate(revised).model_dump(mode="json")
    provider = Scripted()
    revision = Runner(registry, provider).run(config, "idea-revision", {
        "question": "Revise the first idea after Critic feedback", "source_refs": ["macro-calendar"],
        "parent_idea_draft_id": run_id})
    assert revision["events"][-1]["detail"]["status"] == "EXPLORATORY_UNMEASURED"
    lineage = next(event["detail"] for event in revision["events"] if event["kind"] == "IDEA_REVISION")
    assert lineage["parent_draft_id"] == run_id
    assert lineage["parent_critique_sha256"] == registry.get(t.critiques, run_id)["artifact_id"]
    assert revision["research_records"]["draft"]["body"]["related_draft_ids"] == [run_id]
    assert not any(tool["result"].get("error") == "LINEAGE_REFERENCE_NOT_IN_TASK" for tool in revision["tools"])
    assert registry.read(registry.get(t.drafts, run_id)["artifact_id"])["title"] == idea_payload()["title"]
    revision_input = revision["invocations"][1]["request"]["input"][0]["content"]
    assert canonical(registry.read(registry.get(t.critiques, run_id)["artifact_id"])) in revision_input

    def sqlite_bootstrap_append(connection, table, values):
        normalized = {key: val.replace(tzinfo=None) if isinstance(val, datetime) and val.tzinfo else val
                      for key, val in values.items()}
        return append(connection, table, normalized)

    monkeypatch.setattr("ledgerquant.research.bootstrap.append", sqlite_bootstrap_append)
    diagnostic = bootstrap(registry, load_legacy_bundle(private_evidence_root()), profile,
        CampaignPolicy(max_runs=1, max_invocations=1, max_reserved_tokens=10000, max_usd=1),
        "sqlite-diagnostic")
    source_id = revision["run"]["id"]
    measurement_task = {"source_idea_draft_id": source_id,
        "measurement_mapping_reason": "Narrow the event idea to a supported price-only diagnostic; this is a derived question."}
    measured_run, _ = registry.start_run("derived-measurement", diagnostic["campaign_id"], diagnostic["snapshot_id"],
        diagnostic["versions"]["research"], diagnostic["versions"]["critic"], measurement_task)
    linked = Runner(registry, provider)._linked_idea(measured_run, "discovery", measurement_task)
    assert linked["draft_id"] == source_id
    assert linked["measurement_mapping_reason"] == measurement_task["measurement_mapping_reason"]
    with pytest.raises(RegistryError, match="MEASUREMENT_MAPPING_REASON_REQUIRED"):
        Runner(registry, provider)._linked_idea(measured_run, "discovery", {"source_idea_draft_id": source_id})
    proposal = Proposal.model_validate(proposal_payload())
    with engine.begin() as connection:
        proposal_id = artifact(connection, proposal)
        append(connection, t.drafts, {"id": measured_run["id"], "run_id": measured_run["id"],
            "family_id": "eurusd_four_hour_direction", "signature": digest(proposal.diagnostic),
            "artifact_id": proposal_id, "created_at": now()})
        critique = Critique(draft_sha256=proposal_id, disposition="REVIEW", objections=(), summary="Review the derived diagnostic.")
        append(connection, t.critiques, {"id": measured_run["id"], "draft_id": measured_run["id"],
            "artifact_id": artifact(connection, critique), "created_at": now()})
    monkeypatch.setattr("ledgerquant.research.admission._serialize_family", lambda *_: None)
    lock = admit(registry, Admission(draft_id=measured_run["id"], draft_sha256=proposal_id,
        actor="operator", action="ADMIT_DEVELOPMENT", reason="Supported diagnostic only", objection_resolutions={}))
    assert lock["execution_allowed"] is False
    frozen = registry.read(registry.get(t.commitments, measured_run["id"] + ":DESIGN_FREEZE")["artifact_id"])
    assert frozen["origin_idea"]["idea_draft_id"] == source_id
    assert frozen["origin_idea"]["idea_draft_sha256"] == registry.get(t.drafts, source_id)["artifact_id"]
    assert frozen["origin_idea"]["relation"] == "DERIVED_MEASUREMENT_QUESTION"
    measured_report = registry.report(measured_run["id"])
    stored = {item["kind"]: item["body"] for item in measured_report["research_records"]["commitments"]}
    assert stored["DESIGN_FREEZE"]["origin_idea"] == frozen["origin_idea"]
    assert stored["CANDIDATE_LOCK"]["status"] == lock["status"]
    engine.dispose()
