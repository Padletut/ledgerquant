from copy import deepcopy

import pytest
from pydantic import ValidationError

from ledgerquant.research.catalog import Diagnostic
from ledgerquant.research.grounded_proposals import ProposalV3, CritiqueV3, grounding_errors
from ledgerquant.research.scoped_proposals import parse_proposal, parse_critique
from ledgerquant.research.types import digest
from ledgerquant.research.proposals import review
from tests.unit.test_requirement_scope import scoped_proposal


def context_fixture():
    source = Diagnostic(hours_utc=[8, 12, 16]).model_dump(mode="json")
    prior = Diagnostic(hours_utc=[12]).model_dump(mode="json")
    fact = {"evidence_id": "eurusd_four_hour_direction_2021_replication_v1", "evidence_sha256": "a" * 64,
            "source_diagnostic": source, "field": "gate_decision", "value": "TEMPORAL_FAILED"}
    return {"prior_groups": [{"signature": digest(source), "diagnostic": source, "attempts": []},
                             {"signature": digest(prior), "diagnostic": prior, "attempts": []}],
            "facts": {digest(fact): fact}}


def grounded_payload(context=None):
    context = context or context_fixture()
    return {**scoped_proposal(), "schema_version": "research_proposal/3",
            "revision": None,
            "prior_comparisons": [{"signature": group["signature"], "relation": "RELATED_VARIANT",
                "difference": "08 UTC only instead of the recorded hours."} for group in context["prior_groups"]],
            "evidence_claims": [{"fact_id": key, "applies_to": "SOURCE_CONTRACT",
                "interpretation": "Related aggregate evidence; subset performance has not been measured."} for key in context["facts"]],
            "falsification_target": "predictive_performance", "admission_risks": ["No independent window."]}


def critique_payload(proposal):
    return {"schema_version": "research_critique/3", "draft_sha256": digest(proposal), "disposition": "REVIEW",
            "objections": [], "summary": "Related variant, no measured subset result.",
            "requirement_consistency": "CONSISTENT", "requirement_explanation": "Economic costs are deferred.",
            "prior_attempt_consistency": "CONSISTENT", "evidence_attribution": "CONSISTENT",
            "falsifier_consistency": "CONSISTENT", "grounding_explanation": "Checked exact signatures and source scope."}


def test_related_aggregate_evidence_is_valid_but_cannot_certify_subset():
    context = context_fixture()
    payload = grounded_payload(context)
    assert grounding_errors(ProposalV3.model_validate(payload), context) == []
    payload["evidence_claims"][0]["applies_to"] = "PROPOSED_CONTRACT"
    assert "EVIDENCE_SCOPE_MISMATCH" in grounding_errors(ProposalV3.model_validate(payload), context)


def test_prior_inventory_must_be_complete_and_relations_must_match():
    context = context_fixture()
    payload = grounded_payload(context)
    payload["diagnostic"]["hours_utc"] = [12]
    assert "PRIOR_RELATION_MISMATCH" in grounding_errors(ProposalV3.model_validate(payload), context)
    payload["prior_comparisons"].pop()
    assert "PRIOR_INVENTORY_MISMATCH" in grounding_errors(ProposalV3.model_validate(payload), context)


def test_unknown_fact_and_evidence_omission_are_rejected():
    context = context_fixture()
    payload = grounded_payload(context)
    payload["evidence_claims"][0]["fact_id"] = "b" * 64
    assert "UNKNOWN_EVIDENCE_FACT" in grounding_errors(ProposalV3.model_validate(payload), context)
    payload = grounded_payload(context)
    payload["evidence_ids"] = ["unrelated"]
    assert "EVIDENCE_CITATION_MISMATCH" in grounding_errors(ProposalV3.model_validate(payload), context)


def test_current_cost_contradiction_is_a_contract_defect_not_economic_failure():
    context = context_fixture()
    payload = grounded_payload(context)
    payload["data_requirements"][0]["scope"] = "current_diagnostic"
    proposal = ProposalV3.model_validate(payload)
    critique = CritiqueV3.model_validate(critique_payload(proposal))
    result = review(proposal, critique, set(proposal.evidence_ids), set(), context)
    assert result.status == "BLOCKED_CONTRACT_DEFECT"
    assert result.reasons == ("REQUIREMENT_CONTRADICTION",)


def test_critic_can_cite_frozen_facts_but_not_arbitrary_hashes():
    context = context_fixture()
    proposal = ProposalV3.model_validate(grounded_payload(context))
    payload = critique_payload(proposal)
    payload["objections"] = [{"code": "EVIDENCE_SCOPE_MISMATCH", "severity": "advisory",
        "explanation": "Use the explicit source scope.", "evidence_ids": [next(iter(context["facts"]))]}]
    critique = CritiqueV3.model_validate(payload)
    result = review(proposal, critique, set(proposal.evidence_ids), set(), context)
    assert result.status == "AWAITING_OPERATOR_REVIEW"
    assert result.reference_policy == "scoped_registry_references/1"
    payload["objections"][0]["evidence_ids"] = ["f" * 64]
    result = review(proposal, CritiqueV3.model_validate(payload), set(proposal.evidence_ids), set(), context)
    assert result.status == "REJECTED" and "UNKNOWN_EVIDENCE" in result.reasons


def test_v3_critic_records_each_alleged_defect_as_an_objection():
    proposal = ProposalV3.model_validate(grounded_payload())
    base = critique_payload(proposal)
    for field, code in [("prior_attempt_consistency", "PRIOR_RELATION_MISMATCH"),
                        ("evidence_attribution", "EVIDENCE_SCOPE_MISMATCH"),
                        ("falsifier_consistency", "NON_PREDICTIVE_FALSIFIER")]:
        payload = deepcopy(base)
        payload[field] = "CONTRADICTORY"
        with pytest.raises(ValidationError):
            CritiqueV3.model_validate(payload)
        payload["objections"] = [{"code": code, "severity": "material", "explanation": "Explicit defect.", "evidence_ids": []}]
        assert parse_critique(payload).model_dump(mode="json") == payload
    assert digest(parse_proposal(proposal.model_dump(mode="json"))) == digest(proposal)
