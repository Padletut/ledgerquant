"""Repair exposure gate against the real registry; no provider, market or evaluator calls."""

from hashlib import sha256
import json
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from ledgerquant.agents.definitions import CampaignPolicy
from ledgerquant.agents.runtime import Runner
from ledgerquant.agents.tools import ResearchTools
from ledgerquant.models.generation import Generation, ToolCall
from ledgerquant.research import tables as t
from ledgerquant.research.admission import Admission, admit
from ledgerquant.research.bootstrap import bootstrap
from ledgerquant.research.contract_revisions import RevisionSubmission, resolve_revision
from ledgerquant.research.grounding import frozen_context
import ledgerquant.research.admission as admission_module
from ledgerquant.research.imports import load_legacy_bundle
from tests.private_evidence import private_evidence_root
from ledgerquant.research.registry import RegistryError
from ledgerquant.research.repair_exposure import RepairDenied
from ledgerquant.research.review_corrections import ReviewCorrection, correct_review
from ledgerquant.research.scoped_proposals import parse_proposal
from ledgerquant.research.types import canonical, digest
from tests.integration.test_agent_runtime import Scripted, setup
from tests.integration.test_grounded_runtime import GroundedTransport, register_v3
from tests.integration.test_research_registry import registered, start
from tests.integration.test_agent_runtime import setup as legacy_setup
from tests.unit.test_agent_catalog import proposal_payload
from tests.unit.test_grounded_proposals import critique_payload, grounded_payload


LEGACY = ["eurusd_four_hour_direction_2020_v1", "eurusd_four_hour_direction_2021_replication_v1"]


def narrowed_bundle(hours):
    """Test fixture only: the legacy evidence re-declared on other hours so a repair can be unexposed."""
    bundle = load_legacy_bundle(private_evidence_root())
    suffix = "_fixture_hours_" + "_".join(map(str, hours))
    for item, attempt, window in zip(bundle["evidence"], bundle["attempts"], bundle["windows"], strict=True):
        contract = json.loads(attempt["contract"])
        contract["decision_contract"]["candidate_event_rule"]["hours_utc"] = list(hours)
        attempt["contract"] = json.dumps(contract, sort_keys=True)
        attempt["contract_sha256"] = sha256(attempt["contract"].encode()).hexdigest()
        payload = json.loads(item["original"])
        payload["contract_sha256"] = attempt["contract_sha256"]
        item["original"] = json.dumps(payload, sort_keys=True)
        item["sha256"] = sha256(item["original"].encode()).hexdigest()
        item["payload"] = payload
        for record in (item, attempt, window):
            record["id"] += suffix
    return bundle


class StrictTransport(Scripted):
    """Reads only outcome-free views; optionally attempts the prohibited read once per role."""

    def __init__(self, profile, *, attempt_outcome_read=False):
        super().__init__(profile, {})
        self.attempt_outcome_read = attempt_outcome_read

    def invoke(self, request):
        self.count += 1
        if self.count == 1:
            return self._answer("capability_probe", {"answer": "LEDGERQUANT"})
        results = [json.loads(item["result"]) for item in request["input"] if "result" in item]
        sequence = (["read_development_snapshot"] if self.attempt_outcome_read else []) + ["read_source_coverage", "read_released_evidence"]
        if len(results) < len(sequence):
            return self._answer(sequence[len(results)], {})
        if '"draft_sha256"' in request["input"][0]["content"]:
            return self._answer("submit_critique", critique_payload(self.proposal))
        context = next(item["prior_inventory"] for item in results if "prior_inventory" in item)
        context["facts"] = next(item["facts"] for item in results if "facts" in item)
        payload = grounded_payload(context)
        payload["evidence_ids"] = sorted({fact["evidence_id"] for fact in context["facts"].values()})
        parent_id, parent = next(iter(context["revision_parents"].items()))
        for comparison in payload["prior_comparisons"]:
            comparison["relation"] = "SAME_RESEARCH_IDEA" if comparison["signature"] == digest(parent["proposal"]["diagnostic"]) else "RELATED_VARIANT"
        submission = RevisionSubmission(parent_draft_id=parent_id, parent_draft_sha256=parent["draft_sha256"],
            reason="Only repair requirement scope.", admissibility_probability=0.7,
            **{key: payload[key] for key in ("prior_comparisons", "evidence_claims", "falsification_target", "admission_risks")})
        self.proposal = resolve_revision(submission, context).model_dump(mode="json")
        return self._answer("submit_contract_revision", submission)

    def _answer(self, name, payload):
        return Generation("COMPLETED", {"fixture": True}, [], (ToolCall(f"strict-{self.count}", name, canonical(payload)),), 100, 100)


def blocked_parent(registry, profile, bundle, hours, evidence_ids, development_page=None):
    """A v1 attempt blocked by its own binding cost declaration, then annotated as a contract defect."""
    config = bootstrap(registry, bundle, profile, CampaignPolicy(max_runs=1, max_invocations=9, max_reserved_tokens=500000, max_usd=1),
                       "parent-" + uuid4().hex)
    payload = {**proposal_payload(), "diagnostic": {"hours_utc": list(hours)}, "evidence_ids": evidence_ids,
               "data_requirements": [{"source": "broker_costs", "reason": "Only future economics need costs.",
                                      "reactivation_condition": "Reviewed cost evidence."}]}
    provider = Scripted(profile, parse_proposal(payload).model_dump(mode="json"), development_page=development_page)
    report = Runner(registry, provider).run(config, "parent-" + uuid4().hex, {})
    assert report["events"][-1]["detail"]["status"] == "BLOCKED_DATA_REQUIREMENT"
    parent = registry.get(t.drafts, report["run"]["id"])
    original = next(e["detail"] for e in report["events"] if e["kind"] == "CONTRACT_REVIEW")
    corrected = correct_review(registry, ReviewCorrection(draft_id=parent["id"], draft_sha256=parent["artifact_id"],
        original_review_sha256=digest(original), classification="BLOCKED_CONTRACT_DEFECT",
        reason="Binding v1 cost declaration contradicted the price-only scope.", actor="test_operator"))
    return parent, corrected


def repair_task(parent, corrected, policy, reviewer_exposure="NONE_DECLARED"):
    return {"submission_policy": "revision_only", "repair_policy": policy,
            "revision_authorizations": [{"parent_draft_id": parent["id"], "parent_draft_sha256": parent["artifact_id"],
                "scope_changes": [{"requirement_index": 0, "scope": "future_economic"}], "reason": "Correct only cost scope.",
                "defect_reference": {"kind": "CONTRACT_REVIEW_CORRECTION", "sha256": corrected["correction_sha256"],
                                     "classification": "BLOCKED_CONTRACT_DEFECT"},
                "reviewer": "test_operator", "reviewer_outcome_exposure": reviewer_exposure}]}


def admission(draft, action="ADMIT_DEVELOPMENT", reason="Authorized scope-only revision."):
    return Admission(draft_id=draft["id"], draft_sha256=draft["artifact_id"], actor="test_operator",
                     action=action, reason=reason, objection_resolutions={})


def eligibility_of(report, parent):
    context = next(e["detail"] for e in report["events"] if e["kind"] == "GROUNDING_CONTEXT")
    return context, context["revision_parents"][parent["id"]]["repair_eligibility"]


def register_narrowed_v3(registry, profile, bundle):
    return bootstrap(registry, bundle, profile, CampaignPolicy(max_runs=3, max_invocations=30, max_reserved_tokens=1500000, max_usd=1),
                     "narrowed-" + uuid4().hex, contract_version=3)


def test_strict_repair_is_denied_in_the_exposed_family_before_any_provider_call(registered):
    registry, _, profile = registered
    parent, corrected = blocked_parent(registry, profile, load_legacy_bundle(private_evidence_root()), [12], LEGACY)
    config = register_v3(registry, profile)
    strict = StrictTransport(profile)
    report = Runner(registry, strict).run(config, "strict-" + uuid4().hex, repair_task(parent, corrected, "premeasurement_repair"))
    assert strict.count == 0 and report["invocations"] == []
    stopped = report["events"][-1]
    assert stopped["kind"] == "STOPPED" and stopped["detail"]["kind"] == "REPAIR_EXPOSURE_DENIED"
    assert "RELEVANT_OUTCOME_EXPOSED" in stopped["detail"]["reason"] and stopped["detail"]["economic_failure"] is False
    context, eligibility = eligibility_of(report, parent)
    assert eligibility["decision"] == "DENIED" and eligibility["exposure"] == "EXPOSED"
    assert context["version"] == "research_grounding/2" and context["tool_policy"] == "research_tools/1+outcome_free_repair/1"
    kinds = {(item["kind"], item["relevance"]) for item in eligibility["findings"]}
    assert {("LABELLED_CASE_READ", "OVERLAPPING"), ("RELEASED_EVIDENCE", "OVERLAPPING")} <= kinds
    assert {item["role"] for item in eligibility["findings"] if item["kind"] == "LABELLED_CASE_READ"} == {"research", "critic"}
    with pytest.raises(RepairDenied):
        frozen_context(registry, report["run"]["id"])
    with registry.engine.connect() as c:
        assert c.execute(select(t.drafts).where(t.drafts.c.run_id == report["run"]["id"])).first() is None
        assert c.execute(select(func.count()).select_from(t.runs).where(t.runs.c.campaign_id == config["campaign_id"])).scalar_one() == 1
    # The same idea may still proceed as an explicitly exposed corrected attempt; nothing is relabelled.
    model = GroundedTransport(profile, revision=True, fact_citation=True)
    task = repair_task(parent, corrected, "exposed_corrected_attempt", reviewer_exposure="EXPOSED")
    report = Runner(registry, model).run(config, "exposed-" + uuid4().hex, task)
    assert report["events"][-1]["detail"]["status"] == "AWAITING_OPERATOR_REVIEW"
    _, eligibility = eligibility_of(report, parent)
    assert eligibility["decision"] == "EXPOSED_CORRECTED_ATTEMPT" and eligibility["exposure"] == "EXPOSED"
    draft = registry.get(t.drafts, report["run"]["id"])
    lock = admit(registry, admission(draft))
    assert lock["execution_allowed"] is False
    freeze = registry.read(registry.get(t.commitments, draft["id"] + ":DESIGN_FREEZE")["artifact_id"])
    assert freeze["repair_eligibility"]["decision"] == "EXPOSED_CORRECTED_ATTEMPT" and freeze["repair_eligibility"]["exposure"] == "EXPOSED"
    recheck = registry.read(registry.get(t.commitments, draft["id"] + ":REPAIR_ELIGIBILITY_RECHECK")["artifact_id"])
    assert recheck["decision"] == "EXPOSED_CORRECTED_ATTEMPT" and recheck["stage"] == "ADMISSION_RECHECK"


def test_unexposed_strict_repair_runs_outcome_free_and_rechecks_at_admission(registered):
    registry, _, profile = registered
    bundle = narrowed_bundle([8])
    parent, corrected = blocked_parent(registry, profile, bundle, [16], [item["id"] for item in bundle["evidence"]],
                                       development_page={"offset": 0, "limit": 3})
    config = register_narrowed_v3(registry, profile, bundle)
    strict = StrictTransport(profile, attempt_outcome_read=True)
    report = Runner(registry, strict).run(config, "strict-" + uuid4().hex, repair_task(parent, corrected, "premeasurement_repair"))
    final = report["events"][-1]["detail"]
    assert final["status"] == "AWAITING_OPERATOR_REVIEW" and final["attempt_kind"] == "CORRECTED_REVISION"
    _, eligibility = eligibility_of(report, parent)
    assert eligibility["decision"] == "ELIGIBLE_PREMEASUREMENT_REPAIR" and eligibility["exposure"] == "NONE_ESTABLISHED"
    assert {item["kind"] for item in eligibility["findings"]} >= {"RELEASED_EVIDENCE", "LABELLED_CASE_READ"}
    assert all(item["relevance"] == "UNRELATED" for item in eligibility["findings"])
    denied = [tool for tool in report["tools"] if tool["name"] == "read_development_snapshot"]
    assert len(denied) == 2 and all(tool["allowed"] == 0 and tool["result"] == {"error": "OUTCOME_READ_PROHIBITED"} for tool in denied)
    offered = [tool["name"] for tool in report["invocations"][1]["request"]["tools"]]
    assert "read_development_snapshot" not in offered and "submit_contract_revision" in offered
    draft = registry.get(t.drafts, report["run"]["id"])
    command = admission(draft)
    lock = admit(registry, command)
    assert lock["status"] == "NO_INDEPENDENT_WINDOW" and lock["execution_allowed"] is False
    assert admit(registry, command) == lock
    freeze = registry.read(registry.get(t.commitments, draft["id"] + ":DESIGN_FREEZE")["artifact_id"])
    assert freeze["repair_eligibility"]["decision"] == "ELIGIBLE_PREMEASUREMENT_REPAIR"
    recheck = registry.read(registry.get(t.commitments, draft["id"] + ":REPAIR_ELIGIBILITY_RECHECK")["artifact_id"])
    assert recheck["decision"] == "ELIGIBLE_PREMEASUREMENT_REPAIR" and recheck["intervening_findings"] == []
    assert freeze["repair_eligibility"]["recheck_sha256"] == digest(recheck)


def test_intervening_development_result_denies_strict_admission_durably(registered):
    registry, _, profile = registered
    bundle = narrowed_bundle([8])
    parent, corrected = blocked_parent(registry, profile, bundle, [16], [item["id"] for item in bundle["evidence"]],
                                       development_page={"offset": 0, "limit": 3})
    config = register_narrowed_v3(registry, profile, bundle)
    report = Runner(registry, StrictTransport(profile)).run(config, "strict-" + uuid4().hex, repair_task(parent, corrected, "premeasurement_repair"))
    assert report["events"][-1]["detail"]["status"] == "AWAITING_OPERATOR_REVIEW"
    repair = registry.get(t.drafts, report["run"]["id"])
    sibling = Runner(registry, GroundedTransport(profile, hours=[12, 16])).run(config, "sibling-" + uuid4().hex, {})
    assert sibling["events"][-1]["detail"]["status"] == "AWAITING_OPERATOR_REVIEW"
    other = registry.get(t.drafts, sibling["run"]["id"])
    admit(registry, admission(other, reason="Related variant developed before the repair was admitted."))
    command = admission(repair)
    with pytest.raises(RepairDenied, match="RELEVANT_OUTCOME_EXPOSED"):
        admit(registry, command)
    row = registry.get(t.commitments, repair["id"] + ":REPAIR_ELIGIBILITY_RECHECK")
    record = registry.read(row["artifact_id"])
    assert record["decision"] == "DENIED" and record["authorization_decision"] == "ELIGIBLE_PREMEASUREMENT_REPAIR"
    assert any(item["kind"] == "DEVELOPMENT_RESULT" and item["subject"] == other["id"] for item in record["intervening_findings"])
    for kind in ("DESIGN_FREEZE", "OPERATOR_DECISION", "CANDIDATE_LOCK"):
        with pytest.raises(RegistryError, match="unknown commitments"):
            registry.get(t.commitments, repair["id"] + ":" + kind)
    with pytest.raises(RepairDenied):
        admit(registry, command)
    assert registry.get(t.commitments, repair["id"] + ":REPAIR_ELIGIBILITY_RECHECK") == row
    rejected = admit(registry, command.model_copy(update={"action": "REJECT", "reason": "Exposed after authorization."}))
    assert rejected == {"status": "REJECTED", "economic_failure": False}


def test_strict_task_needs_a_recorded_defect_reference_and_an_explicit_policy(registered):
    registry, _, profile = registered
    parent, corrected = blocked_parent(registry, profile, load_legacy_bundle(private_evidence_root()), [12], LEGACY)
    config = register_v3(registry, profile)
    wrong = repair_task(parent, corrected, "premeasurement_repair")
    wrong["revision_authorizations"][0]["defect_reference"]["sha256"] = "f" * 64
    transport = StrictTransport(profile)
    report = Runner(registry, transport).run(config, "wrong-" + uuid4().hex, wrong)
    assert report["events"][-1]["detail"]["reason"] == "DEFECT_REFERENCE_INVALID"
    missing = repair_task(parent, corrected, "premeasurement_repair")
    del missing["repair_policy"]
    report = Runner(registry, transport).run(config, "missing-" + uuid4().hex, missing)
    assert report["events"][-1]["detail"]["reason"] == "REPAIR_POLICY_REQUIRED"
    assert transport.count == 0


def test_raw_task_policy_cannot_relax_required_reads_outside_a_validated_v3_context(registered):
    """A legacy run never freezes a repair context, so the task field alone must change nothing."""
    registry, config, _ = registered
    run, _ = registry.start_run(uuid4().hex, config["campaign_id"], config["snapshot_id"], config["versions"]["research"],
                                config["versions"]["critic"], {"repair_policy": "premeasurement_repair", "submission_policy": "revision_only"})
    call = registry.reserve_invocation(run["id"], config["versions"]["research"], 0, {})
    tools = ResearchTools(registry, run["id"], "research")
    assert tools.prohibited == set() and "read_development_snapshot" in [item["name"] for item in tools.schemas()]
    for name in ("read_source_coverage", "read_released_evidence"):
        assert "error" not in tools.execute(call["id"], name, {})
    assert tools.execute(call["id"], "submit_hypothesis_draft", proposal_payload())["error"] == "REQUIRED_EVIDENCE_NOT_READ"
    page = tools.execute(call["id"], "read_development_snapshot", {"offset": 0, "limit": 1})
    assert page["total_cases"] == 390 and "error" not in page


def test_labelled_reads_by_abandoned_or_unlisted_runs_deny_strict_repair(registered):
    registry, _, profile = registered
    bundle = narrowed_bundle([8])
    parent, corrected = blocked_parent(registry, profile, bundle, [16], [item["id"] for item in bundle["evidence"]],
                                       development_page={"offset": 0, "limit": 3})
    # An abandoned legacy run reads labelled 16 UTC cases and never submits anything.
    abandoned_config = bootstrap(registry, bundle, profile, CampaignPolicy(max_runs=1, max_invocations=3, max_reserved_tokens=100000, max_usd=1),
                                 "abandoned-" + uuid4().hex)
    run, _ = start(registry, abandoned_config)
    call = registry.reserve_invocation(run["id"], abandoned_config["versions"]["research"], 0, {})
    reader = ResearchTools(registry, run["id"], "research")
    page = reader.execute(call["id"], "read_development_snapshot", {"offset": 3, "limit": 3})
    assert any(case["target"] and case["anchor_utc"].endswith("16:00:00Z") for case in page["cases"])
    config = register_narrowed_v3(registry, profile, bundle)
    report = Runner(registry, StrictTransport(profile)).run(config, "strict-" + uuid4().hex, repair_task(parent, corrected, "premeasurement_repair"))
    assert report["events"][-1]["detail"]["kind"] == "REPAIR_EXPOSURE_DENIED"
    _, eligibility = eligibility_of(report, parent)
    exposing = [item for item in eligibility["findings"] if item["relevance"] == "OVERLAPPING"]
    assert exposing and all(item["kind"] == "LABELLED_CASE_READ" and item["subject"] == run["id"] and item["lineage"] == "OTHER_RUN" for item in exposing)
    # A different-signature variant that read the same labelled population is exposure too.
    variant = Runner(registry, GroundedTransport(profile, hours=[12, 16])).run(config, "variant-" + uuid4().hex, {})
    assert variant["events"][-1]["detail"]["status"] == "AWAITING_OPERATOR_REVIEW"
    report = Runner(registry, StrictTransport(profile)).run(config, "strict2-" + uuid4().hex, repair_task(parent, corrected, "premeasurement_repair"))
    _, eligibility = eligibility_of(report, parent)
    subjects = {item["subject"] for item in eligibility["findings"] if item["relevance"] == "OVERLAPPING"}
    assert {run["id"], variant["run"]["id"]} <= subjects


def test_resumed_development_keeps_the_frozen_design_that_predates_later_exposure(registered, monkeypatch):
    registry, _, profile = registered
    bundle = narrowed_bundle([8])
    parent, corrected = blocked_parent(registry, profile, bundle, [16], [item["id"] for item in bundle["evidence"]],
                                       development_page={"offset": 0, "limit": 3})
    config = register_narrowed_v3(registry, profile, bundle)
    report = Runner(registry, StrictTransport(profile)).run(config, "strict-" + uuid4().hex, repair_task(parent, corrected, "premeasurement_repair"))
    repair = registry.get(t.drafts, report["run"]["id"])
    command = admission(repair)
    real_develop = admission_module.develop

    def interrupted(*args, **kwargs):
        raise RuntimeError("simulated crash after the atomic admission transaction")
    monkeypatch.setattr(admission_module, "develop", interrupted)
    with pytest.raises(RuntimeError):
        admit(registry, command)
    freeze = registry.get(t.commitments, repair["id"] + ":DESIGN_FREEZE")
    recheck = registry.get(t.commitments, repair["id"] + ":REPAIR_ELIGIBILITY_RECHECK")
    assert registry.read(recheck["artifact_id"])["decision"] == "ELIGIBLE_PREMEASUREMENT_REPAIR"
    monkeypatch.setattr(admission_module, "develop", real_develop)
    sibling = Runner(registry, GroundedTransport(profile, hours=[12, 16])).run(config, "sibling-" + uuid4().hex, {})
    other = registry.get(t.drafts, sibling["run"]["id"])
    admit(registry, admission(other, reason="Overlapping variant developed after the repair froze."))
    later = registry.get(t.commitments, other["id"] + ":DEVELOPMENT_RESULT")
    assert freeze["created_at"] < later["created_at"]
    lock = admit(registry, command)
    assert lock["design_sha256"] == digest(registry.read(freeze["artifact_id"]))
    assert registry.get(t.commitments, repair["id"] + ":REPAIR_ELIGIBILITY_RECHECK") == recheck
    assert registry.get(t.commitments, repair["id"] + ":DESIGN_FREEZE") == freeze

