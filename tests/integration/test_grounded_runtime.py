import json
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from ledgerquant.agents.definitions import CampaignPolicy
from ledgerquant.agents.runtime import Runner
from ledgerquant.models.generation import Generation, ToolCall
from ledgerquant.research import tables as t
from ledgerquant.research.admission import Admission, admit
from ledgerquant.research.bootstrap import bootstrap
from ledgerquant.research.contract_revisions import RevisionSubmission, resolve_revision
from ledgerquant.research.grounding import frozen_context, build_context
from ledgerquant.research.grounded_proposals import ProposalV3
from ledgerquant.research.imports import load_legacy_bundle
from ledgerquant.research.registry import RegistryError, now
from ledgerquant.research.review_corrections import ReviewCorrection, correct_review
from ledgerquant.research.types import canonical, digest
from tests.integration.test_agent_runtime import Scripted, setup
from tests.integration.test_research_registry import registered
from tests.unit.test_grounded_proposals import grounded_payload, critique_payload
from tests.unit.test_agent_catalog import proposal_payload


class GroundedTransport(Scripted):
    def __init__(self, profile, *, revision=False, misattribute=False, fact_citation=False):
        super().__init__(profile, {})
        self.revision, self.misattribute = revision, misattribute
        self.fact_citation = fact_citation

    def invoke(self, request):
        if self.count == 4:
            results = [json.loads(item["result"]) for item in request["input"] if "result" in item]
            context = next(item["prior_inventory"] for item in results if "prior_inventory" in item)
            context["facts"] = next(item["facts"] for item in results if "facts" in item)
            payload = grounded_payload(context)
            payload["evidence_ids"] = sorted({fact["evidence_id"] for fact in context["facts"].values()})
            if self.misattribute:
                payload["evidence_claims"][0]["applies_to"] = "PROPOSED_CONTRACT"
            if self.revision:
                parent_id, parent = next(iter(context["revision_parents"].items()))
                for comparison in payload["prior_comparisons"]:
                    comparison["relation"] = "SAME_RESEARCH_IDEA" if comparison["signature"] == digest(parent["proposal"]["diagnostic"]) else "RELATED_VARIANT"
                submission = RevisionSubmission(parent_draft_id=parent_id, parent_draft_sha256=parent["draft_sha256"],
                    reason="Only repair requirement scope.", admissibility_probability=0.7,
                    **{key: payload[key] for key in ("prior_comparisons", "evidence_claims", "falsification_target", "admission_risks")})
                self.proposal = resolve_revision(submission, context).model_dump(mode="json")
                return self._answer("submit_contract_revision", submission)
            self.proposal = ProposalV3.model_validate(payload).model_dump(mode="json")
        if self.count == 8:
            critique = critique_payload(self.proposal)
            if self.fact_citation:
                critique["objections"] = [{"code": "EVIDENCE_SCOPE_MISMATCH", "severity": "advisory",
                    "explanation": "Keep source scope explicit.", "evidence_ids": [self.proposal["evidence_claims"][0]["fact_id"]]}]
            return self._answer("submit_critique", critique)
        return super().invoke(request)

    def _answer(self, name, payload):
        self.count += 1
        return Generation("COMPLETED", {"fixture": True}, [], (ToolCall(str(self.count), name, canonical(payload)),), 100, 100)


def register_v3(registry, profile):
    return bootstrap(registry, load_legacy_bundle(Path(__file__).parents[2]), profile,
        CampaignPolicy(max_runs=2, max_invocations=20, max_reserved_tokens=1000000, max_usd=1),
        "grounded-" + uuid4().hex, contract_version=3)


def test_corrected_revision_keeps_parent_and_can_freeze_develop_and_lock(registered):
    payload = proposal_payload()
    payload["diagnostic"] = {"hours_utc": [12]}
    payload["evidence_ids"] = ["eurusd_four_hour_direction_2020_v1", "eurusd_four_hour_direction_2021_replication_v1"]
    payload["data_requirements"] = [{"source": "broker_costs", "reason": "Only future economics need costs.", "reactivation_condition": "Reviewed cost evidence."}]
    registry, legacy_config, provider = setup(registered, payload)
    old = Runner(registry, provider).run(legacy_config, "parent-" + uuid4().hex, {})
    parent = registry.get(t.drafts, old["run"]["id"])
    original = next(e["detail"] for e in old["events"] if e["kind"] == "CONTRACT_REVIEW")
    correction = ReviewCorrection(draft_id=parent["id"], draft_sha256=parent["artifact_id"], original_review_sha256=digest(original),
        classification="BLOCKED_CONTRACT_DEFECT", reason="Binding v1 cost declaration contradicted diagnostic scope.", actor="test_operator")
    assert correct_review(registry, correction)["admission_granted"] is False
    assert registry.report(parent["run_id"])["current_integrity"]["status"] == "REVIEW_REQUIRED"
    config = register_v3(registry, provider.profile)
    task = {"submission_policy": "revision_only", "revision_authorizations": [{"parent_draft_id": parent["id"], "parent_draft_sha256": parent["artifact_id"],
        "scope_changes": [{"requirement_index": 0, "scope": "future_economic"}], "reason": "Correct only cost scope."}]}
    model = GroundedTransport(provider.profile, revision=True, fact_citation=True)
    report = Runner(registry, model).run(config, "revision-" + uuid4().hex, task)
    assert report["events"][-1]["detail"]["status"] == "AWAITING_OPERATOR_REVIEW"
    assert report["events"][-1]["detail"]["attempt_kind"] == "CORRECTED_REVISION"
    context = next(e["detail"] for e in report["events"] if e["kind"] == "GROUNDING_CONTEXT")
    assert frozen_context(registry, report["run"]["id"]) == context
    assert report["run"]["id"] not in canonical(context)
    draft = registry.get(t.drafts, report["run"]["id"])
    assert draft["signature"] == parent["signature"]
    command = Admission(draft_id=draft["id"], draft_sha256=draft["artifact_id"], actor="test_operator",
        action="ADMIT_DEVELOPMENT", reason="Authorized scope-only revision; unchanged exposure.", objection_resolutions={})
    lock = admit(registry, command)
    assert lock["execution_allowed"] is False
    assert lock["status"] == "NO_INDEPENDENT_WINDOW"
    assert admit(registry, command) == lock
    assert registry.read(parent["artifact_id"]) == provider.proposal
    with registry.engine.connect() as c:
        assert len(c.execute(select(t.drafts)).all()) == 2
        assert all(row.state == "CONSUMED" for row in c.execute(select(t.windows)))
        manifest = registry.read(registry.get(t.snapshots, config["snapshot_id"])["manifest_id"])
        later_context = build_context(c, manifest, now(), "later-run")
        attempt = next(item for group in later_context["prior_groups"] for item in group["attempts"] if item["id"] == draft["id"])
        assert attempt["status"] == "NO_INDEPENDENT_WINDOW"
        assert attempt["original_contract_status"] == "AWAITING_OPERATOR_REVIEW"
        assert "DEVELOPMENT_RESULT" in attempt["commitment_refs"]
    replay = Runner(registry, model).run(config, report["run"]["command_key"], task)
    assert replay == report and model.count == 9


def test_service_rejects_aggregate_claim_even_when_critic_recommends_review(registered):
    registry, _, profile = registered
    config = register_v3(registry, profile)
    report = Runner(registry, GroundedTransport(profile, misattribute=True)).run(config, "scope-" + uuid4().hex, {})
    assert "EVIDENCE_SCOPE_MISMATCH" in report["events"][-1]["detail"]["reasons"]
    draft = registry.get(t.drafts, report["run"]["id"])
    with pytest.raises(RegistryError, match="CONTRACT_NOT_ADMISSIBLE"):
        admit(registry, Admission(draft_id=draft["id"], draft_sha256=draft["artifact_id"], actor="test_operator",
            action="ADMIT_DEVELOPMENT", reason="Invalid attribution", objection_resolutions={}))
