"""Exposure assessment is a service decision; agents and reviewers cannot shrink it."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from ledgerquant.research.contract_revisions import RevisionAuthorization, corrected_fields, resolve_revision, revision_errors
from ledgerquant.research.proposals import Proposal
from ledgerquant.research.repair_exposure import (assessment, combined_exposure, finding, labelled_overlap, recheck,
                                                  registry_exposure)
from ledgerquant.research.types import digest
from tests.unit.test_agent_catalog import proposal_payload
from tests.unit.test_contract_revisions import revision_context, revision_request


CUTOFF = datetime(2026, 10, 10, tzinfo=timezone.utc)


def parent_record(hours=(16,)):
    proposal = Proposal.model_validate({**proposal_payload(), "diagnostic": {"hours_utc": list(hours)},
        "data_requirements": [{"source": "broker_costs", "reason": "Deferred economic prerequisite.",
                               "reactivation_condition": "Verified broker costs."}]}).model_dump(mode="json")
    return {"draft_id": "parent", "draft_sha256": digest(proposal), "proposal": proposal,
            "scope_changes": [{"requirement_index": 0, "scope": "future_economic"}], "reason": "Reviewed cost-scope defect."}


def authorization(**changes):
    return RevisionAuthorization.model_validate({"parent_draft_id": "parent", "parent_draft_sha256": "a" * 64,
        "scope_changes": [{"requirement_index": 0, "scope": "future_economic"}], "reason": "Repair only the cost declaration.",
        "defect_reference": {"kind": "CONTRACT_REVIEW_CORRECTION", "sha256": "b" * 64, "classification": "BLOCKED_CONTRACT_DEFECT"},
        "reviewer": "test_operator", "reviewer_outcome_exposure": "NONE_DECLARED", **changes})


def labelled_read(hours_seen, run_id="parent-run", labelled=True):
    cases = [{"case_id": f"EURUSD:2020-01-02T{hour:02d}:00:00Z", "anchor_utc": f"2020-01-02T{hour:02d}:00:00Z",
              "status": "MEASURABLE" if labelled else "INPUT_MISSING", "target": "PREDICT_UP" if labelled else None}
             for hour in hours_seen]
    return cases


def assess(policy, findings, hours=(16,), submission_policy="revision_only", **auth_changes):
    return assessment(policy, parent_record(hours), hours, findings, authorization(**auth_changes), CUTOFF, submission_policy)


def test_authorization_requires_reviewed_defect_reference_and_reviewer_declaration():
    for missing in ("defect_reference", "reviewer", "reviewer_outcome_exposure"):
        payload = authorization().model_dump(mode="json")
        payload.pop(missing)
        with pytest.raises(ValidationError):
            RevisionAuthorization.model_validate(payload)
    with pytest.raises(ValidationError):
        authorization(defect_reference={"kind": "CONTRACT_REVIEW", "sha256": "b" * 64, "classification": "COST_FAILURE"})


def test_unexposed_repair_is_eligible_only_on_the_strict_route_with_full_record():
    strict = assess("premeasurement_repair", [])
    assert strict["decision"] == "ELIGIBLE_PREMEASUREMENT_REPAIR" and strict["exposure"] == "NONE_ESTABLISHED"
    assert strict["tool_policy"] == "research_tools/1+outcome_free_repair/1"
    assert strict["substantive_diff"] == [{"requirement_index": 0, "source": "broker_costs", "before": "current_diagnostic", "after": "future_economic"}]
    assert strict["corrected_contract_sha256"] == digest(corrected_fields(parent_record()["proposal"], parent_record()["scope_changes"]))
    assert strict["model_knowledge"] == "UNASSESSED_SEPARATE_FACT" and strict["reviewer"] == "test_operator"
    exposed = assess("exposed_corrected_attempt", [])
    assert exposed["decision"] == "EXPOSED_CORRECTED_ATTEMPT" and exposed["tool_policy"] == "research_tools/1"


def test_labelled_case_pages_count_as_outcomes_only_when_hours_overlap():
    assert labelled_overlap(labelled_read([8, 12, 16]), (16,)) == 1
    assert labelled_overlap(labelled_read([16], labelled=False), (16,)) == 0
    overlapping = [finding("LABELLED_CASE_READ", "parent-run", "c" * 64, "2026-10-09T00:00:00+00:00", "OVERLAPPING",
                           role="research", cases_read=10, labelled_overlapping_cases=3)]
    denied = assess("premeasurement_repair", overlapping)
    assert denied["decision"] == "DENIED" and denied["reasons"] == ["RELEVANT_OUTCOME_EXPOSED"]
    attempt = assess("exposed_corrected_attempt", overlapping)
    assert attempt["decision"] == "EXPOSED_CORRECTED_ATTEMPT" and attempt["exposure"] == "EXPOSED"
    unrelated = [finding("LABELLED_CASE_READ", "other-run", "c" * 64, "2026-10-09T00:00:00+00:00", "UNRELATED",
                         role="critic", cases_read=3, labelled_overlapping_cases=0)]
    assert assess("premeasurement_repair", unrelated)["decision"] == "ELIGIBLE_PREMEASUREMENT_REPAIR"


def test_measured_results_and_released_aggregates_overlapping_the_hours_are_exposure():
    for kind in ("DEVELOPMENT_RESULT", "CANDIDATE_LOCK", "RELEASED_EVIDENCE"):
        item = finding(kind, "subject", "d" * 64, "2026-10-09T00:00:00+00:00", "OVERLAPPING", hours_utc=[8, 12, 16])
        assert assess("premeasurement_repair", [item])["decision"] == "DENIED"


def test_unknown_exposure_blocks_the_strict_route_and_is_never_lifted_by_absence():
    assert registry_exposure([]) == "NONE_ESTABLISHED"
    unknown = [finding("PARTICIPANT_RUN", "missing-run", None, None, "UNKNOWN")]
    assert registry_exposure(unknown) == "UNKNOWN"
    denied = assess("premeasurement_repair", unknown)
    assert denied["decision"] == "DENIED" and denied["reasons"] == ["EXPOSURE_UNKNOWN"]
    assert registry_exposure(unknown + [finding("DEVELOPMENT_RESULT", "d", "e" * 64, "t", "OVERLAPPING")]) == "EXPOSED"
    assert combined_exposure("NONE_ESTABLISHED", "UNKNOWN") == "UNKNOWN"
    assert combined_exposure("UNKNOWN", "EXPOSED") == "EXPOSED"
    assert combined_exposure("EXPOSED", "NONE_DECLARED") == "EXPOSED"


def test_reviewer_declared_exposure_and_wrong_submission_policy_deny_strict_repair():
    declared = assess("premeasurement_repair", [], reviewer_outcome_exposure="UNKNOWN")
    assert declared["decision"] == "DENIED" and declared["reasons"] == ["EXPOSURE_UNKNOWN", "REVIEWER_EXPOSURE_UNKNOWN"]
    assert assess("premeasurement_repair", [], reviewer_outcome_exposure="EXPOSED")["exposure"] == "EXPOSED"
    policy = assess("premeasurement_repair", [], submission_policy="proposal_or_authorized_revision")
    assert policy["decision"] == "DENIED" and policy["reasons"] == ["REVISION_ONLY_REQUIRED"]
    assert assess("exposed_corrected_attempt", [], reviewer_outcome_exposure="EXPOSED")["decision"] == "EXPOSED_CORRECTED_ATTEMPT"


def test_admission_recheck_denies_intervening_exposure_and_keeps_prior_denial():
    frozen = assess("premeasurement_repair", [])
    assert recheck(frozen, [], CUTOFF, "test_operator")["decision"] == "ELIGIBLE_PREMEASUREMENT_REPAIR"
    intervening = finding("DEVELOPMENT_RESULT", "sibling", "f" * 64, "2026-10-10T00:00:00+00:00", "OVERLAPPING", hours_utc=[12, 16])
    denied = recheck(frozen, [intervening], CUTOFF, "test_operator")
    assert denied["decision"] == "DENIED" and denied["intervening_findings"] == [intervening]
    assert denied["authorization_sha256"] == digest(frozen) and denied["stage"] == "ADMISSION_RECHECK"
    previously = recheck({**frozen, "decision": "DENIED"}, [], CUTOFF, "test_operator")
    assert previously["decision"] == "DENIED" and "AUTHORIZATION_DENIED" in previously["reasons"]
    exposed = recheck(assess("exposed_corrected_attempt", []), [intervening], CUTOFF, "test_operator")
    assert exposed["decision"] == "EXPOSED_CORRECTED_ATTEMPT" and exposed["exposure"] == "EXPOSED"


def test_denied_eligibility_blocks_submission_and_review_of_the_authorized_revision():
    context = revision_context()
    context["revision_parents"]["parent-attempt"]["repair_eligibility"] = {"decision": "DENIED", "reasons": ["RELEVANT_OUTCOME_EXPOSED"]}
    with pytest.raises(ValueError, match="REPAIR_EXPOSURE_DENIED"):
        resolve_revision(revision_request(context), context)
    eligible = revision_context()
    proposal = resolve_revision(revision_request(eligible), eligible)
    assert revision_errors(proposal, context) == ["REPAIR_EXPOSURE_DENIED"]
    assert revision_errors(proposal, eligible) == []


def test_changed_payoff_or_source_disguised_as_repair_is_not_a_cost_scope_correction():
    parent = {**proposal_payload(), "data_requirements": [{"source": "raw_news", "reason": "Needs news.",
                                                           "reactivation_condition": "PIT news source."}]}
    with pytest.raises(ValueError, match="REVISION_NOT_A_COST_SCOPE_CORRECTION"):
        corrected_fields(parent, [{"requirement_index": 0, "scope": "future_economic"}])
    with pytest.raises(ValueError, match="INVALID_REVISION_PATCH"):
        corrected_fields(parent_record()["proposal"], [{"requirement_index": 2, "scope": "future_economic"}])
