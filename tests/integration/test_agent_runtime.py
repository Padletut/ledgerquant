"""Scripted transport exercises orchestration, not model research ability."""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from ledgerquant.agents.definitions import CampaignPolicy
from ledgerquant.agents.runtime import Runner
from ledgerquant.models.generation import Generation, ToolCall
from ledgerquant.research import tables as t
from ledgerquant.research.admission import Admission, admit
from ledgerquant.research.bootstrap import bootstrap, invalidate_evidence
from ledgerquant.research.imports import load_legacy_bundle
from ledgerquant.research.registry import RegistryError
from ledgerquant.research.types import canonical, digest
from tests.integration.test_research_registry import registered
from tests.unit.test_agent_catalog import proposal_payload


class Scripted:
    def __init__(self, profile, proposal, *, timeout=False):
        self.profile, self.proposal, self.timeout = profile, proposal, timeout
        self.count = 0

    def prepare(self, instructions, conversation, tools):
        return {"instructions": instructions, "input": conversation, "tools": tools}

    def user_message(self, value):
        return {"role": "user", "content": value}

    def tool_result(self, call_id, result):
        return {"call_id": call_id, "result": result}

    def invoke(self, request):
        self.count += 1
        if self.timeout:
            raise TimeoutError("do not retry me")
        if self.count == 1:
            name, arguments = "capability_probe", {"answer": "LEDGERQUANT"}
        else:
            step = (self.count - 2) % 4
            names = ["read_source_coverage", "read_released_evidence", "read_development_snapshot"]
            if step < 3:
                name, arguments = names[step], {}
            elif self.count == 5:
                name, arguments = "submit_hypothesis_draft", self.proposal
            else:
                name = "submit_critique"
                arguments = {"draft_sha256": digest(self.proposal), "disposition": "REVIEW", "objections": [], "summary": "Supported bounded diagnostic."}
        call = ToolCall("scripted-" + str(self.count), name, canonical(arguments))
        return Generation("COMPLETED", {"fixture": True, "call": name, "arguments": arguments}, [], (call,), 100, 100)


def setup(registered, payload=None):
    registry, _, profile = registered
    config = bootstrap(registry, load_legacy_bundle(Path(__file__).parents[2]), profile,
        CampaignPolicy(max_runs=1, max_invocations=9, max_reserved_tokens=500000, max_usd=1), "runtime-" + uuid4().hex)
    payload = payload or proposal_payload()
    # Normalize defaults so the scripted Critic cites the actual submitted hash.
    from ledgerquant.research.proposals import Proposal
    provider = Scripted(profile, Proposal.model_validate(payload).model_dump(mode="json"))
    return registry, config, provider


def test_full_loop_replay_and_fresh_critic_context(registered):
    registry, config, provider = setup(registered)
    runner = Runner(registry, provider)
    report = runner.run(config, "run-" + config["campaign_id"], {"purpose": "engineering_fixture"})
    assert provider.count == 9
    assert report["events"][-1]["kind"] == "FINISHED"
    critic_request = report["invocations"][5]["request"]
    assert len(critic_request["input"]) == 1
    assert "draft_sha256" in critic_request["input"][0]["content"]
    replay = runner.run(config, report["run"]["command_key"], {"purpose": "engineering_fixture"})
    assert replay == report
    assert provider.count == 9


def test_timeout_persists_and_redelivery_does_not_dispatch(registered):
    registry, config, provider = setup(registered)
    provider.timeout = True
    runner = Runner(registry, provider)
    report = runner.run(config, "timeout-" + config["campaign_id"], {})
    assert report["invocations"][0]["outcome"]["status"] == "DISPATCH_UNKNOWN"
    assert report["events"][-1]["detail"]["economic_failure"] is False
    runner.run(config, report["run"]["command_key"], {})
    assert provider.count == 1


def test_duplicate_is_retained_and_cannot_be_admitted(registered):
    payload = proposal_payload()
    payload["diagnostic"]["hours_utc"] = [8, 12, 16]
    registry, config, provider = setup(registered, payload)
    report = Runner(registry, provider).run(config, "duplicate-" + config["campaign_id"], {})
    assert report["events"][-1]["detail"]["status"] == "REJECTED"
    draft = registry.get(t.drafts, report["run"]["id"])
    with pytest.raises(RegistryError, match="CONTRACT_NOT_ADMISSIBLE"):
        admit(registry, Admission(draft_id=draft["id"], draft_sha256=draft["artifact_id"], actor="test_operator",
            action="ADMIT_DEVELOPMENT", reason="test", objection_resolutions={}))


def test_operator_freezes_then_develops_and_locks_without_validation(registered):
    registry, config, provider = setup(registered)
    report = Runner(registry, provider).run(config, "admit-" + config["campaign_id"], {})
    draft = registry.get(t.drafts, report["run"]["id"])
    decision = Admission(draft_id=draft["id"], draft_sha256=draft["artifact_id"], actor="test_operator",
        action="ADMIT_DEVELOPMENT", reason="No unsupported blocking objection", objection_resolutions={})
    lock = admit(registry, decision)
    assert lock["status"] == "NO_INDEPENDENT_WINDOW"
    assert lock["execution_allowed"] is False
    assert admit(registry, decision) == lock
    freeze = registry.get(t.commitments, draft["id"] + ":DESIGN_FREEZE")
    result = registry.get(t.commitments, draft["id"] + ":DEVELOPMENT_RESULT")
    assert freeze["created_at"] < result["created_at"]


def test_data_block_retained_and_invalidation_marks_dependencies(registered):
    payload = proposal_payload()
    payload["data_requirements"] = [{"source": "raw_news", "reason": "Needs source observations",
                                     "reactivation_condition": "PIT news source registered"}]
    registry, config, provider = setup(registered, payload)
    report = Runner(registry, provider).run(config, "blocked-" + config["campaign_id"], {})
    assert report["events"][-1]["detail"]["status"] == "BLOCKED_DATA_REQUIREMENT"
    invalidate_evidence(registry, "eurusd_four_hour_direction_2021_replication_v1", "test source correction", "test_operator")
    corrected = registry.report(report["run"]["id"])
    assert corrected["current_integrity"]["status"] == "REVIEW_REQUIRED"
    assert corrected["events"] == report["events"]
    assert corrected["tools"] == report["tools"]
