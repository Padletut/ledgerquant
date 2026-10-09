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


def review(proposal: Proposal, critique: Critique, evidence_ids: set[str], known_signatures: set[str]) -> ReviewDecision:
    from .catalog import classify
    from .types import digest
    from .scoped_proposals import ProposalV2, CritiqueV2

    scoped = isinstance(proposal, ProposalV2)
    if scoped != isinstance(critique, CritiqueV2):
        raise ValueError("proposal and critique contract versions differ")
    current = tuple(item for item in proposal.data_requirements
                    if not scoped or item.scope == "current_diagnostic")
    family, loop, signature = classify(proposal.diagnostic)
    if critique.draft_sha256 != digest(proposal):
        raise ValueError("critique refers to a different draft")
    references = set(proposal.evidence_ids) | {ref for item in critique.objections for ref in item.evidence_ids}
    reasons = []
    if not references <= evidence_ids:
        reasons.append("UNKNOWN_EVIDENCE")
    if signature in known_signatures or loop == "DUPLICATE":
        reasons.append("DUPLICATE")
    if scoped and any(item.source == "broker_costs" for item in current):
        reasons.append("REQUIREMENT_CONTRADICTION")
    if reasons:
        status = "REJECTED"
    elif current:
        status, reasons = "BLOCKED_DATA_REQUIREMENT", ["SOURCE_UNAVAILABLE"]
    else:
        status, reasons = "AWAITING_OPERATOR_REVIEW", ["CRITIQUE_RECORDED_NOT_AN_APPROVAL"]
    return ReviewDecision(status=status, reasons=tuple(reasons), family_id=family, signature=signature, loop=loop)
