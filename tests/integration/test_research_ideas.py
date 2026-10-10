"""Requires RESEARCH_TEST_DATABASE_URL for a disposable migrated research_test database."""

from uuid import uuid4

import pytest
from sqlalchemy import select

from ledgerquant.agents.definitions import CampaignPolicy
from ledgerquant.agents.runtime import Runner
from ledgerquant.agents.tools import ResearchTools
from ledgerquant.models.generation import Generation, ToolCall
from ledgerquant.research import tables as t
from ledgerquant.research.admission import Admission, admit
from ledgerquant.research.bootstrap import bootstrap
from ledgerquant.research.registry import RegistryError
from ledgerquant.research.types import canonical, digest
from tests.integration.test_research_registry import registered
from tests.unit.test_research_ideas import idea_payload


class IdeaProvider:
    def __init__(self, profile, proposal):
        self.profile, self.proposal, self.calls = profile, proposal, 0

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
            name, arguments = "submit_research_idea", self.proposal
        else:
            name, arguments = "submit_idea_critique", {"draft_sha256": digest(self.proposal),
                "summary": "Requires an event-time source and reviewed evaluator.",
                "concerns": ["Current event data and costs are unverified."], "source_refs": []}
        return Generation("COMPLETED", {"fixture": name}, [],
            (ToolCall("idea-" + str(self.calls), name, canonical(arguments)),), 100, 100)


def test_idea_and_critique_recorded_without_evaluation_or_eurusd_bundle(registered):
    registry, _, profile = registered
    config = bootstrap(registry, None, profile,
        CampaignPolicy(max_runs=1, max_invocations=3, max_reserved_tokens=100000, max_usd=1),
        "idea-" + uuid4().hex, workflow="idea_exploration")
    task = {"question": "Explore macro event decisions", "source_refs": ["macro-calendar"]}
    proposal = idea_payload()
    provider = IdeaProvider(profile, proposal)
    report = Runner(registry, provider).run(config, "idea-run-" + uuid4().hex, task)
    assert report["events"][-1]["detail"]["status"] == "EXPLORATORY_UNMEASURED"
    assert provider.calls == 3
    run_id = report["run"]["id"]
    draft = registry.get(t.drafts, run_id)
    assert draft["family_id"] == "unassigned:" + run_id
    assert registry.read(draft["artifact_id"])["question"] == proposal["question"]
    assert registry.get(t.critiques, run_id)["draft_id"] == run_id
    with registry.engine.connect() as connection:
        assert connection.execute(select(t.commitments.c.id).where(t.commitments.c.draft_id == run_id)).all() == []
    with pytest.raises(RegistryError, match="EXPLORATORY_IDEA_NOT_EVALUABLE"):
        admit(registry, Admission(draft_id=run_id, draft_sha256=draft["artifact_id"], actor="operator",
            action="ADMIT_DEVELOPMENT", reason="Must not enter the EURUSD evaluator", objection_resolutions={}))
    replay = Runner(registry, provider).run(config, report["run"]["command_key"], task)
    assert replay == report
    assert provider.calls == 3


def test_idea_source_refs_and_lineage_are_checked_before_storage(registered):
    registry, _, profile = registered
    config = bootstrap(registry, None, profile,
        CampaignPolicy(max_runs=1, max_invocations=1, max_reserved_tokens=100000, max_usd=1),
        "idea-check-" + uuid4().hex, workflow="idea_exploration")
    run, _ = registry.start_run(uuid4().hex, config["campaign_id"], config["snapshot_id"],
        config["versions"]["research"], config["versions"]["critic"],
        {"question": "Explore", "source_refs": ["macro-calendar"]})
    invocation = registry.reserve_invocation(run["id"], config["versions"]["research"], 0, {})
    tools = ResearchTools(registry, run["id"], "research")
    for key, invalid in (("source_refs", ["invented-source"]), ("related_draft_ids", ["missing-draft"])):
        assert "error" in tools.execute(invocation["id"], "submit_research_idea", {**idea_payload(), key: invalid})
        with registry.engine.connect() as connection:
            assert connection.execute(select(t.drafts.c.id).where(t.drafts.c.run_id == run["id"])).scalar_one_or_none() is None
    assert tools.execute(invocation["id"], "submit_research_idea", idea_payload())["status"] == "EXPLORATORY_UNMEASURED"
