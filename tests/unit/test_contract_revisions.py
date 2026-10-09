from copy import deepcopy

from ledgerquant.research.contract_revisions import RevisionSubmission, resolve_revision, revision_errors
from ledgerquant.research.proposals import Proposal, review
from ledgerquant.research.grounded_proposals import CritiqueV3
from ledgerquant.research.types import digest
from tests.unit.test_agent_catalog import proposal_payload
from tests.unit.test_grounded_proposals import context_fixture, grounded_payload, critique_payload


def revision_context():
    context = context_fixture()
    parent = Proposal.model_validate({**proposal_payload(), "diagnostic": {"hours_utc": [12]},
        "data_requirements": [{"source": "broker_costs", "reason": "Deferred economic prerequisite.",
            "reactivation_condition": "Verified broker costs for a later economic contract."}]}).model_dump(mode="json")
    context["revision_parents"] = {"parent-attempt": {"draft_id": "parent-attempt", "draft_sha256": digest(parent),
        "proposal": parent, "scope_changes": [{"requirement_index": 0, "scope": "future_economic"}],
        "reason": "Operator-authorized correction of binding v1 cost declaration."}}
    return context


def revision_request(context):
    fields = grounded_payload(context)
    for item in fields["prior_comparisons"]:
        item["relation"] = "SAME_RESEARCH_IDEA" if item["signature"] == digest(context["revision_parents"]["parent-attempt"]["proposal"]["diagnostic"]) else "RELATED_VARIANT"
    return RevisionSubmission(parent_draft_id="parent-attempt", parent_draft_sha256=context["revision_parents"]["parent-attempt"]["draft_sha256"],
        reason="Correct cost scope without changing the market idea.", admissibility_probability=0.7,
        **{key: fields[key] for key in ("prior_comparisons", "evidence_claims", "falsification_target", "admission_risks")})


def test_same_idea_corrected_attempt_can_be_admitted_without_erasing_parent():
    context = revision_context()
    proposal = resolve_revision(revision_request(context), context)
    assert revision_errors(proposal, context) == []
    critique = CritiqueV3.model_validate(critique_payload(proposal))
    result = review(proposal, critique, set(proposal.evidence_ids), {digest(proposal.diagnostic)}, context)
    assert result.status == "AWAITING_OPERATOR_REVIEW"
    assert result.attempt_kind == "CORRECTED_REVISION"
    assert result.parent_draft_id == "parent-attempt"
    assert result.idea_relation == "SAME_RESEARCH_IDEA"
    assert "scope" not in context["revision_parents"]["parent-attempt"]["proposal"]["data_requirements"][0]


def test_revision_cannot_change_horizon_hours_sources_or_parent_identity():
    context = revision_context()
    proposal = resolve_revision(revision_request(context), context)
    for update in ({"diagnostic": proposal.diagnostic.model_copy(update={"hours_utc": (8,)})},
                   {"support": ("Silently replace the parent's rationale.",)},
                   {"revision": proposal.revision.model_copy(update={"parent_draft_sha256": "f" * 64})}):
        assert revision_errors(proposal.model_copy(update=update), context)
    unauthorized = deepcopy(context)
    unauthorized["revision_parents"] = {}
    assert "REVISION_NOT_AUTHORIZED" in revision_errors(proposal, unauthorized)


def test_same_diagnostic_without_revision_link_remains_duplicate():
    context = revision_context()
    proposal = resolve_revision(revision_request(context), context).model_copy(update={"revision": None})
    critique = CritiqueV3.model_validate(critique_payload(proposal))
    result = review(proposal, critique, set(proposal.evidence_ids), {digest(proposal.diagnostic)}, context)
    assert result.status == "REJECTED"
    assert "DUPLICATE" in result.reasons
