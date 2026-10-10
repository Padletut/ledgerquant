"""Model-authored proposals and critiques contain no authority over evidence."""

from typing import Literal

from pydantic import Field

from .catalog import Diagnostic
from .types import Record


class DataRequirement(Record):
    source: Literal["raw_news", "historical_sentiment", "broker_costs"]
    reason: str = Field(min_length=1, max_length=1000)
    reactivation_condition: str = Field(min_length=1, max_length=1000)


class Proposal(Record):
    title: str = Field(min_length=1, max_length=200)
    diagnostic: Diagnostic
    mechanism: str = Field(min_length=1, max_length=2000)
    support: tuple[str, ...] = Field(min_length=1, max_length=8)
    contrary_evidence: tuple[str, ...] = Field(min_length=1, max_length=8)
    falsifier: str = Field(min_length=1, max_length=2000)
    predicted_failure: Literal["TEMPORAL_FAILURE", "INSUFFICIENT_SUPPORT", "DATA_QUALITY_FAILURE", "COST_UNVERIFIED"]
    admissibility_probability: float = Field(ge=0, le=1, allow_inf_nan=False)
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=8)
    data_requirements: tuple[DataRequirement, ...] = Field(max_length=3)


class Objection(Record):
    code: Literal["DUPLICATE", "SOURCE_UNSUPPORTED", "TEMPORAL_FAILURE", "INSUFFICIENT_SUPPORT", "COST_UNVERIFIED", "UNSUPPORTED_CLAIM", "MISSING_COUNTEREVIDENCE"]
    severity: Literal["blocking", "material", "advisory"]
    explanation: str = Field(min_length=1, max_length=2000)
    evidence_ids: tuple[str, ...] = Field(max_length=8)


class Critique(Record):
    draft_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    disposition: Literal["REVIEW", "REJECT", "BLOCKED_DATA_REQUIREMENT"]
    objections: tuple[Objection, ...] = Field(max_length=10)
    summary: str = Field(min_length=1, max_length=3000)


class ReviewDecision(Record):
    status: Literal["REJECTED", "BLOCKED_DATA_REQUIREMENT", "AWAITING_OPERATOR_REVIEW"]
    reasons: tuple[str, ...]
    family_id: str
    signature: str
    loop: str


def requirement_scope_error(proposal: Proposal) -> bool:
    """A current broker-cost input contradicts the price-only diagnostic."""
    from .scoped_proposals import ProposalV2

    return isinstance(proposal, ProposalV2) and any(
        item.source == "broker_costs" and item.scope == "current_diagnostic"
        for item in proposal.data_requirements
    )


def review(proposal: Proposal, critique: Critique, evidence_ids: set[str], known_signatures: set[str], grounding=None) -> ReviewDecision:
    from .catalog import classify
    from .types import digest
    from .scoped_proposals import ProposalV2, CritiqueV2
    from .grounded_proposals import ProposalV3, CritiqueV3, ReviewDecisionV3, grounding_errors
    from .contract_revisions import revision_errors

    scoped = isinstance(proposal, ProposalV2)
    if scoped != isinstance(critique, CritiqueV2) or isinstance(proposal, ProposalV3) != isinstance(critique, CritiqueV3):
        raise ValueError("proposal and critique contract versions differ")
    current = tuple(item for item in proposal.data_requirements
                    if not scoped or item.scope == "current_diagnostic")
    family, loop, signature = classify(proposal.diagnostic)
    if critique.draft_sha256 != digest(proposal):
        raise ValueError("critique refers to a different draft")
    critic_references = {ref for item in critique.objections for ref in item.evidence_ids}
    allowed_critic_references = set(evidence_ids)
    reasons = []
    corrected_revision = False
    if isinstance(proposal, ProposalV3):
        if grounding is None:
            raise ValueError("v3 review requires frozen grounding context")
        reasons.extend(grounding_errors(proposal, grounding))
        defects = revision_errors(proposal, grounding)
        reasons.extend(defects)
        corrected_revision = proposal.revision is not None and not defects
        allowed_critic_references.update(key for key, fact in grounding["facts"].items()
            if key == digest(fact) and fact["evidence_id"] in evidence_ids)
    if not set(proposal.evidence_ids) <= evidence_ids or not critic_references <= allowed_critic_references:
        reasons.append("UNKNOWN_EVIDENCE")
    if (signature in known_signatures or loop == "DUPLICATE") and not corrected_revision:
        reasons.append("DUPLICATE")
    if requirement_scope_error(proposal):
        reasons.append("REQUIREMENT_CONTRADICTION")
    if reasons:
        status = "REJECTED"
    elif current:
        status, reasons = "BLOCKED_DATA_REQUIREMENT", ["SOURCE_UNAVAILABLE"]
    else:
        status, reasons = "AWAITING_OPERATOR_REVIEW", ["CRITIQUE_RECORDED_NOT_AN_APPROVAL"]
    fields = dict(status=status, reasons=tuple(reasons), family_id=family, signature=signature, loop=loop)
    if isinstance(proposal, ProposalV3):
        if reasons == ["REQUIREMENT_CONTRADICTION"]:
            fields["status"] = "BLOCKED_CONTRACT_DEFECT"
        return ReviewDecisionV3(**fields, idea_relation="SAME_RESEARCH_IDEA" if signature in known_signatures or loop == "DUPLICATE" else "RELATED_VARIANT",
            attempt_kind="CORRECTED_REVISION" if corrected_revision else "NEW_PROPOSAL",
            parent_draft_id=proposal.revision.parent_draft_id if proposal.revision else None,
            reference_policy="scoped_registry_references/1")
    return ReviewDecision(**fields)
