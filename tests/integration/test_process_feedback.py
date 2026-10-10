"""Process assessments are sealed from outcomes; feedback is typed, reviewed and policy-selected."""

from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from ledgerquant.agents.definitions import CampaignPolicy
from ledgerquant.agents.runtime import Runner
from ledgerquant.research import tables as t
from ledgerquant.research.admission import Admission, admit
from ledgerquant.research.bootstrap import bootstrap, invalidate_evidence
from ledgerquant.research.feedback import Feedback, FeedbackPolicy, feedback_state, record_feedback, select_feedback
from ledgerquant.research.grounding import build_context
from ledgerquant.research.imports import load_legacy_bundle
from ledgerquant.research.process_assessment import (Finding, ProcessAssessment, assess_process, assessment_state,
                                                     resolve_reference, sealed_packet)
from ledgerquant.research.registry import RegistryError, now
from ledgerquant.research.review_corrections import ReviewCorrection, correct_review
from ledgerquant.research.types import digest
from tests.integration.test_agent_runtime import Scripted, setup
from tests.integration.test_grounded_runtime import GroundedTransport, register_v3
from tests.integration.test_research_registry import registered
from tests.unit.test_agent_catalog import proposal_payload


ROOT = Path(__file__).parents[2]


def packet_for(registry, run_id, role):
    with registry.engine.connect() as c:
        packet = sealed_packet(c, run_id, role)
    return packet, digest(packet)


def assessment(packet, role, findings, **changes):
    base = {"run_id": packet["run_id"], "role": role, "draft_sha256": packet["draft"]["sha256"],
            "critique_sha256": packet["critique"]["sha256"] if packet["critique"] else None, "packet_sha256": digest(packet),
            "rubric_version": "process_rubric/1", "assessment_mode": "RETROSPECTIVE_SEALED_PACKET",
            "assessor": "test_assessor", "assessor_outcome_exposure": "NONE_DECLARED", "review_state": "REVIEWED",
            "reviewer": "test_reviewer", "findings": findings, "limitations": ["Fixture rubric; not a model-quality label."],
            "reason": "Fixture assessment of a recorded action."}
    return ProcessAssessment.model_validate({**base, **changes})


def scope_finding(status="SUPPORTED", component="research", references=("draft.data_requirements[0]",)):
    return {"code": "REQUIREMENT_SCOPE_CONFUSION", "status": status, "responsible_component": component, "severity": "material",
            "references": list(references), "applicability": "Binding cost declaration versus stated price-only scope.",
            "explanation": "The draft declared broker costs as required although the narrative defers them."}


def blocked_cost_run(registered):
    payload = {**proposal_payload(), "diagnostic": {"hours_utc": [12]},
               "data_requirements": [{"source": "broker_costs", "reason": "Only future economics need costs.",
                                      "reactivation_condition": "Reviewed cost evidence."}]}
    registry, config, provider = setup(registered, payload)
    report = Runner(registry, provider).run(config, "assess-" + uuid4().hex, {})
    assert report["events"][-1]["detail"]["status"] == "BLOCKED_DATA_REQUIREMENT"
    return registry, report["run"]["id"], registry.get(t.drafts, report["run"]["id"])


def test_sealed_packet_excludes_later_outcomes_and_assessment_is_outcome_invariant(registered):
    registry, config, provider = setup(registered)
    report = Runner(registry, provider).run(config, "clean-" + uuid4().hex, {})
    run_id = report["run"]["id"]
    before, before_hash = packet_for(registry, run_id, "research")
    assert before["critique"] is None and before["current_service_checks"]["status"] == "AWAITING_OPERATOR_REVIEW"
    assert {item["name"] for item in before["tool_results"]} == {"read_source_coverage", "read_released_evidence", "read_development_snapshot"}
    valid = assess_process(registry, assessment(before, "research", [scope_finding("NOT_SUPPORTED", references=("draft.data_requirements",))]))
    draft = registry.get(t.drafts, run_id)
    lock = admit(registry, Admission(draft_id=draft["id"], draft_sha256=draft["artifact_id"], actor="test_operator",
                                     action="ADMIT_DEVELOPMENT", reason="Fixture development.", objection_resolutions={}))
    assert lock["status"] == "NO_INDEPENDENT_WINDOW"
    after, after_hash = packet_for(registry, run_id, "research")
    assert after_hash == before_hash
    development = registry.get(t.commitments, draft["id"] + ":DEVELOPMENT_RESULT")["artifact_id"]
    assert development not in digest(after) and development not in str(after)
    again = assess_process(registry, assessment(after, "research", [scope_finding("NOT_SUPPORTED", references=("draft.data_requirements",))]))
    assert again["assessment_id"] == valid["assessment_id"] and again["assessment_sha256"] == valid["assessment_sha256"]
    with pytest.raises(RegistryError, match="REFERENCE_OUTSIDE_PACKET"):
        assess_process(registry, assessment(after, "research", [scope_finding("SUPPORTED", references=(development,))]))
    critic, _ = packet_for(registry, run_id, "critic")
    assert critic["critique"]["sha256"] == registry.get(t.critiques, draft["id"])["artifact_id"]
    assert resolve_reference(critic, "critique.objections") == "critique" and resolve_reference(critic, "task.nope") is None


def test_agent_labels_need_action_references_valid_context_and_an_independent_assessor(registered):
    registry, run_id, draft = blocked_cost_run(registered)
    packet, _ = packet_for(registry, run_id, "research")
    assert packet["recorded_contract_review"]["status"] == "BLOCKED_DATA_REQUIREMENT"
    with pytest.raises(RegistryError, match="AGENT_FINDING_NEEDS_ACTION_REFERENCE"):
        assess_process(registry, assessment(packet, "research", [scope_finding(references=("recorded_contract_review.status",))]))
    with pytest.raises(RegistryError, match="PACKET_HASH_MISMATCH"):
        assess_process(registry, assessment(packet, "research", [scope_finding()], packet_sha256="0" * 64))
    research_version = registry.get(t.runs, run_id)["research_version"]
    with pytest.raises(RegistryError, match="SELF_CERTIFICATION_REJECTED"):
        assess_process(registry, assessment(packet, "research", [scope_finding()], assessor=research_version))
    recorded = assess_process(registry, assessment(packet, "research", [scope_finding()]))
    with registry.engine.connect() as c:
        state = assessment_state(c, recorded["assessment_id"])
    assert state == {**state, "state": "CURRENT", "reasons": []}
    critic_packet, _ = packet_for(registry, run_id, "critic")
    critic = assess_process(registry, assessment(critic_packet, "critic",
        [scope_finding(component="critic", references=("critique.summary", "draft.data_requirements[0]"))],
        critic_delta=[{"code": "REQUIREMENT_SCOPE_CONFUSION", "research_assessment_id": recorded["assessment_id"], "effect": "MISSED"}]))
    assert critic["findings"] == 1
    with pytest.raises(RegistryError, match="CRITIC_DELTA_LINK_INVALID"):
        assess_process(registry, assessment(critic_packet, "critic", [], reason="Bad link.",
            critic_delta=[{"code": "REQUIREMENT_SCOPE_CONFUSION", "research_assessment_id": "missing", "effect": "MISSED"}]))
    from ledgerquant.research.process_corrections import invalidate_suite
    registry.event(run_id, "PROCESS_CONTEXT_INVALIDATED", {"reason": "fixture harness defect", "actor": "test_operator"})
    invalid_packet, _ = packet_for(registry, run_id, "research")
    assert invalid_packet["test_basis"]["context_invalidated"] is True
    with pytest.raises(RegistryError, match="INVALID_CONTEXT_YIELDS_NO_AGENT_LABEL"):
        assess_process(registry, assessment(invalid_packet, "research", [scope_finding()], reason="After invalidation."))
    harness = assess_process(registry, assessment(invalid_packet, "research", [scope_finding("UNRESOLVED", "test_harness")],
                                                  reason="Harness defect; no agent label.", supersedes=recorded["assessment_id"]))
    with registry.engine.connect() as c:
        assert assessment_state(c, recorded["assessment_id"])["reasons"] == ["SUPERSEDED", "SOURCE_CONTEXT_INVALIDATED"]
        assert "SOURCE_CONTEXT_INVALIDATED" in assessment_state(c, harness["assessment_id"])["reasons"]
    with pytest.raises(RegistryError, match="ALREADY_SUPERSEDED"):
        assess_process(registry, assessment(invalid_packet, "research", [], reason="Second supersession.", supersedes=recorded["assessment_id"]))


def test_disputed_checker_output_cannot_confirm_an_agent_error(registered):
    registry, _, profile = registered
    config = register_v3(registry, profile)
    report = Runner(registry, GroundedTransport(profile, fact_citation=True)).run(config, "cite-" + uuid4().hex, {})
    assert report["events"][-1]["detail"]["status"] == "AWAITING_OPERATOR_REVIEW"
    draft = registry.get(t.drafts, report["run"]["id"])
    packet, _ = packet_for(registry, report["run"]["id"], "critic")
    assert packet["test_basis"]["disputed_service_output"] is False
    # A later annotation that the checker, not Critic, was wrong suspends agent labels built on that output.
    original = next(e["detail"] for e in report["events"] if e["kind"] == "CONTRACT_REVIEW")
    with pytest.raises(RegistryError, match="CORRECTION_CLASSIFICATION_MISMATCH"):
        correct_review(registry, ReviewCorrection(draft_id=draft["id"], draft_sha256=draft["artifact_id"], original_review_sha256=digest(original),
            classification="CITATION_NAMESPACE_DEFECT", reason="not applicable here", actor="test_operator"))
    finding = {"code": "EVIDENCE_MISATTRIBUTION", "status": "SUPPORTED", "responsible_component": "critic", "severity": "material",
               "references": ["recorded_contract_review.reasons"], "applicability": "Citation namespace.", "explanation": "Checker output only."}
    with pytest.raises(RegistryError, match="AGENT_FINDING_NEEDS_ACTION_REFERENCE"):
        assess_process(registry, assessment(packet, "critic", [finding]))
    disputed = {**packet, "test_basis": {**packet["test_basis"], "disputed_service_output": True}}
    from ledgerquant.research.process_assessment import assessment_errors
    command = assessment(disputed, "critic", [{**finding, "references": ["critique.objections[0]", "recorded_contract_review.reasons"]}])
    assert "DISPUTED_LABEL_CANNOT_CONFIRM_AGENT_ERROR" in assessment_errors(command, disputed)


def test_feedback_types_have_distinct_sources_eligibility_and_policy_selection(registered):
    registry, run_id, draft = blocked_cost_run(registered)
    packet, _ = packet_for(registry, run_id, "research")
    proposed = assess_process(registry, assessment(packet, "research", [scope_finding()], review_state="PROPOSED", reviewer=None))
    source = {"kind": "PROCESS_ASSESSMENT", "id": proposed["assessment_id"], "sha256": proposed["assessment_sha256"]}
    lesson = {"feedback_type": "METHOD_LESSON", "claim": "Declare deferred costs as future_economic, never as a current requirement.",
              "applicability": "Price-only catalog proposals with deferred cost prerequisites.", "counterexamples": [],
              "sources": [source], "author": "test_author", "reviewer": "test_reviewer", "reason": "Reviewed scope defect."}
    with pytest.raises(RegistryError, match="METHOD_LESSON_REQUIRES_REVIEWED_CURRENT_ASSESSMENT:NOT_REVIEWED"):
        record_feedback(registry, Feedback.model_validate(lesson))
    reviewed = assess_process(registry, assessment(packet, "research", [scope_finding()], supersedes=proposed["assessment_id"]))
    lesson["sources"] = [{"kind": "PROCESS_ASSESSMENT", "id": reviewed["assessment_id"], "sha256": reviewed["assessment_sha256"]}]
    recorded = record_feedback(registry, Feedback.model_validate(lesson))
    assert recorded["release_state"] == "RELEASED" and recorded["lineage_key"] == "process:" + run_id
    duplicate_narrative = record_feedback(registry, Feedback.model_validate({**lesson, "claim": "Same lesson, other words."}))
    assert duplicate_narrative["lineage_key"] == recorded["lineage_key"]
    evidence = registry.get(t.evidence, "eurusd_four_hour_direction_2021_replication_v1")
    finding = Feedback.model_validate({"feedback_type": "EMPIRICAL_FINDING",
        "claim": "The all-hours rule failed temporal validation in 2021 under its frozen contract.",
        "applicability": "That exact rule, window and baseline; not every hour subset.", "counterexamples": [],
        "sources": [{"kind": "EVIDENCE", "id": evidence["id"], "sha256": evidence["artifact_id"]}],
        "author": "test_author", "reviewer": "test_reviewer", "reason": "Released evaluator record."})
    empirical = record_feedback(registry, finding)
    assert registry.read(empirical["feedback_sha256"])["evidence_scope"][0]["gate_decision"] == "TEMPORAL_FAILED"
    with pytest.raises(ValueError, match="explicitly untested"):
        Feedback.model_validate({**finding.model_dump(mode="json"), "feedback_type": "CAUSAL_CONJECTURE", "sources": [source]})
    conjecture = record_feedback(registry, Feedback.model_validate({"feedback_type": "CAUSAL_CONJECTURE",
        "claim": "Momentum weakened because of a regime change in 2021.", "applicability": "Speculative; not established.",
        "counterexamples": ["No identifying evidence."], "sources": [{"kind": "EVIDENCE", "id": evidence["id"], "sha256": evidence["artifact_id"]}],
        "proposed_test": "A separately registered child hypothesis with regime-conditioned windows.", "untested": True,
        "author": "test_author", "reviewer": "test_reviewer", "reason": "Recorded as a conjecture only."}))
    with pytest.raises(ValueError, match="excluded from established-method feedback"):
        FeedbackPolicy(version="reviewed_method_feedback/1", allowed_types=("METHOD_LESSON", "CAUSAL_CONJECTURE"), context_limit=5)
    policy = FeedbackPolicy(version="reviewed_method_feedback/1", allowed_types=("METHOD_LESSON", "EMPIRICAL_FINDING"), context_limit=5)
    with registry.engine.connect() as c:
        items, manifest = select_feedback(c, policy, now())
        assert [item["id"] for item in items] == [recorded["feedback_id"], empirical["feedback_id"]]
        assert {item["id"]: item["reasons"] for item in manifest["excluded"]} == {duplicate_narrative["feedback_id"]: ["SAME_ROOT_LINEAGE_ALREADY_SELECTED"]}
        assert manifest["assembled_input_sha256"] == digest(items)
        early, early_manifest = select_feedback(c, policy, now() - timedelta(days=1))
        assert early == [] and early_manifest["selected"] == []
        opt_in = FeedbackPolicy(version="reviewed_method_feedback/1", allowed_types=("CAUSAL_CONJECTURE",), include_conjectures=True, context_limit=5)
        marked, _ = select_feedback(c, opt_in, now())
        assert marked[0]["id"] == conjecture["feedback_id"] and marked[0]["untested"] is True and "proposed_test" in marked[0]
    invalidate_evidence(registry, evidence["id"], "fixture source correction", "test_operator")
    with registry.engine.connect() as c:
        rows = {row["id"]: row for row in c.execute(select(t.feedback)).mappings()}
        assert feedback_state(c, rows[empirical["feedback_id"]]) == {"state": "SUSPENDED", "reasons": ["SOURCE_EVIDENCE_INVALIDATED"]}
        assert feedback_state(c, rows[recorded["feedback_id"]])["state"] == "RELEASED"
    original = next(e["detail"] for e in registry.report(run_id)["events"] if e["kind"] == "CONTRACT_REVIEW")
    correct_review(registry, ReviewCorrection(draft_id=draft["id"], draft_sha256=draft["artifact_id"], original_review_sha256=digest(original),
        classification="BLOCKED_CONTRACT_DEFECT", reason="Label corrected after the assessment.", actor="test_operator"))
    with registry.engine.connect() as c:
        rows = {row["id"]: row for row in c.execute(select(t.feedback)).mappings()}
        assert feedback_state(c, rows[recorded["feedback_id"]]) == {"state": "SUSPENDED", "reasons": ["SOURCE_LABEL_CORRECTED_PENDING_REVIEW"]}


def test_frozen_context_supplies_feedback_only_under_a_policy_and_records_the_manifest(registered):
    registry, run_id, _ = blocked_cost_run(registered)
    packet, _ = packet_for(registry, run_id, "research")
    reviewed = assess_process(registry, assessment(packet, "research", [scope_finding()]))
    lesson = record_feedback(registry, Feedback.model_validate({"feedback_type": "METHOD_LESSON",
        "claim": "Deferred costs belong in future_economic scope.", "applicability": "Price-only proposals.", "counterexamples": [],
        "sources": [{"kind": "PROCESS_ASSESSMENT", "id": reviewed["assessment_id"], "sha256": reviewed["assessment_sha256"]}],
        "author": "test_author", "reviewer": "test_reviewer", "reason": "Reviewed."}))
    config = register_v3(registry, registered[2])
    manifest = registry.read(registry.get(t.snapshots, config["snapshot_id"])["manifest_id"])
    with registry.engine.connect() as c:
        history_only = build_context(c, manifest, now(), "later-run")
        assert history_only["feedback"]["arm"] == "HISTORY_ONLY" and history_only["feedback"]["items"] == []
        with_methods = build_context(c, manifest, now(), "later-run", {"feedback_policy": {
            "version": "reviewed_method_feedback/1", "allowed_types": ["METHOD_LESSON"], "context_limit": 3}})
        assert with_methods["feedback"]["arm"] == "HISTORY_PLUS_REVIEWED_METHODS"
        assert [item["id"] for item in with_methods["feedback"]["items"]] == [lesson["feedback_id"]]
        assert with_methods["feedback"]["manifest"]["selected"][0]["sha256"] == lesson["feedback_sha256"]
        with pytest.raises(ValueError):
            build_context(c, manifest, now(), "later-run", {"feedback_policy": {"version": "reviewed_method_feedback/1",
                                                                              "allowed_types": ["CAUSAL_CONJECTURE"], "context_limit": 3}})
    report = Runner(registry, GroundedTransport(registered[2])).run(config, "fed-" + uuid4().hex, {"feedback_policy": {
        "version": "reviewed_method_feedback/1", "allowed_types": ["METHOD_LESSON"], "context_limit": 3}})
    coverage = next(tool for tool in report["tools"] if tool["name"] == "read_source_coverage")
    assert coverage["result"]["method_feedback"]["arm"] == "HISTORY_PLUS_REVIEWED_METHODS"
    assert coverage["result"]["method_feedback"]["items"][0]["claim"] == "Deferred costs belong in future_economic scope."
