import pytest
from pydantic import ValidationError

from ledgerquant.agents.tools import ResearchTools
from ledgerquant.research.proposals import Critique, Proposal, review, requirement_scope_error
from ledgerquant.research.scoped_proposals import ProposalV2, CritiqueV2, parse_proposal, parse_critique
from ledgerquant.research.types import digest
from tests.unit.test_agent_catalog import proposal_payload


def scoped_proposal(scope="future_economic", source="broker_costs"):
    return {**proposal_payload(), "schema_version": "research_proposal/2", "data_requirements": [
        {"source": source, "scope": scope, "reason": "Needed only for economic interpretation.",
         "reactivation_condition": "Register independently measured source evidence."}]}


def critique_for(proposal, **changes):
    return CritiqueV2(draft_sha256=digest(proposal), disposition="REVIEW", objections=(),
        summary="Price diagnostic only.", schema_version="research_critique/2",
        requirement_consistency="CONSISTENT", requirement_explanation="Future cost evidence is explicitly deferred.", **changes)


def test_future_costs_do_not_block_current_price_diagnostic():
    proposal = ProposalV2.model_validate(scoped_proposal())
    decision = review(proposal, critique_for(proposal), set(proposal.evidence_ids), set())
    assert decision.status == "AWAITING_OPERATOR_REVIEW"


def test_current_missing_source_blocks_but_current_costs_contradict_catalog():
    for source, status, reason in [("raw_news", "BLOCKED_DATA_REQUIREMENT", "SOURCE_UNAVAILABLE"),
                                   ("broker_costs", "REJECTED", "REQUIREMENT_CONTRADICTION")]:
        proposal = ProposalV2.model_validate(scoped_proposal("current_diagnostic", source))
        result = review(proposal, critique_for(proposal), set(proposal.evidence_ids), set())
        assert (result.status, result.reasons) == (status, (reason,))


def test_only_current_cost_requirement_needs_field_correction():
    assert requirement_scope_error(ProposalV2.model_validate(scoped_proposal("current_diagnostic", "broker_costs")))
    assert not requirement_scope_error(ProposalV2.model_validate(scoped_proposal("future_economic", "broker_costs")))
    assert not requirement_scope_error(ProposalV2.model_validate(scoped_proposal("current_diagnostic", "raw_news")))


def test_current_cost_field_returns_retryable_feedback_before_persistence():
    tools = ResearchTools.__new__(ResearchTools)
    tools.contract_version = 2
    tools.required_reads = set()
    tools.reads = set()
    tools.submission_policy = "proposal_or_authorized_revision"
    tools.submitted = False
    result = tools._perform_in_transaction(None, "submit_hypothesis_draft",
        ProposalV2.model_validate(scoped_proposal("current_diagnostic")))
    assert result["error"] == "REQUIREMENT_CONTRADICTION"
    assert result["field"] == "data_requirements"
    assert tools.submitted is False


def test_scope_is_required_and_never_inferred_from_prose():
    payload = scoped_proposal()
    del payload["data_requirements"][0]["scope"]
    with pytest.raises(ValidationError):
        parse_proposal(payload)
    with pytest.raises(ValueError):
        parse_proposal({**payload, "schema_version": "research_proposal/99"})


def test_historical_proposal_and_critique_hashes_do_not_gain_new_defaults():
    proposal = Proposal.model_validate(proposal_payload())
    payload = proposal.model_dump(mode="json")
    assert digest(parse_proposal(payload)) == digest(payload)
    assert "schema_version" not in parse_proposal(payload).model_dump()
    old = Critique(draft_sha256=digest(proposal), disposition="REVIEW", objections=(), summary="Legacy.")
    assert digest(parse_critique(old.model_dump())) == digest(old)
    assert review(proposal, old, set(proposal.evidence_ids), set()).status == "AWAITING_OPERATOR_REVIEW"


def test_critic_must_record_material_objection_for_narrative_contradiction():
    proposal = ProposalV2.model_validate(scoped_proposal())
    payload = critique_for(proposal).model_dump(mode="json")
    payload["requirement_consistency"] = "CONTRADICTORY"
    with pytest.raises(ValidationError):
        parse_critique(payload)
    payload["objections"] = [{"code": "REQUIREMENT_CONTRADICTION", "severity": "material",
        "explanation": "Narrative uses news today but structured scope defers it.", "evidence_ids": []}]
    critic = parse_critique(payload)
    # Semantic judgement requires operator resolution, not automatic model authority.
    assert review(proposal, critic, set(proposal.evidence_ids), set()).status == "AWAITING_OPERATOR_REVIEW"
    with pytest.raises(ValueError, match="contract versions"):
        review(proposal, Critique(draft_sha256=digest(proposal), disposition="REVIEW", objections=(), summary="Old."), set(proposal.evidence_ids), set())
