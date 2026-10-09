"""V3 proposals reference immutable facts and compare the full prior inventory."""

from typing import Literal

from pydantic import Field, model_validator

from .scoped_proposals import ProposalV2, CritiqueV2, ObjectionV2
from .proposals import ReviewDecision
from .types import Record, digest


GROUNDING_RULES = """Use the frozen grounding context supplied by the service.
Compare the entire normalized diagnostic against EVERY prior signature, including
blocked and rejected drafts. Record one prior_comparison per signature. A renamed
identical diagnostic is SAME_RESEARCH_IDEA. An explicitly
authorized cost-scope correction is a new linked attempt of that SAME idea:
Research uses submit_contract_revision with the parent ID/hash, never renames it
as new. Critic reviews the resolved draft. A correctly linked, authorized revision
can receive REVIEW despite identical diagnostic identity; an unlinked repeat is
still a duplicate new-proposal attempt.
The service applies only the authorized requirement-scope patch and preserves
the parent's diagnostic, rationale, sources, falsifier and consumed exposure.
Inherited narrative keeps the parent's original wording and beliefs; the new
attempt's admissibility_probability is a separately recorded current belief.
A different
hour subset is RELATED_VARIANT in the same exposed family, never a new holdout.
The unused_catalog_hours list identifies unproposed catalog variants, not winners.
Evidence claims reference fact_id values, never invented measurements. Cite facts
from every released evidence record, including failures. SOURCE_CONTRACT means
the fact measures only its recorded source diagnostic, window and baseline.
PROPOSED_CONTRACT requires that exact diagnostic; an all-hours measurement cannot
be attributed to a subset. Related evidence motivates a test but does not measure
the proposed variant. Do not restate aggregate performance as subset performance
in any narrative field. Keep predictive falsification separate from admission
risks: a duplicate, missing source or administrative rejection does not falsify
predictive value. Critic checks prior comparisons, factual attribution and the
falsifier explicitly and records material objections for contradictions.
"""


class PriorComparison(Record):
    signature: str = Field(pattern=r"^[a-f0-9]{64}$")
    relation: Literal["SAME_RESEARCH_IDEA", "RELATED_VARIANT"]
    difference: str = Field(min_length=1, max_length=1000)


class EvidenceClaim(Record):
    fact_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    applies_to: Literal["SOURCE_CONTRACT", "PROPOSED_CONTRACT"]
    interpretation: str = Field(min_length=1, max_length=1000)


class GroundingDeclaration(Record):
    prior_comparisons: tuple[PriorComparison, ...] = Field(min_length=1, max_length=7)
    evidence_claims: tuple[EvidenceClaim, ...] = Field(min_length=1, max_length=16)
    falsification_target: Literal["predictive_performance"]
    admission_risks: tuple[str, ...] = Field(min_length=1, max_length=8)


class ScopeChange(Record):
    requirement_index: int = Field(ge=0, le=2)
    scope: Literal["future_economic"]


class RevisionLink(Record):
    parent_draft_id: str = Field(min_length=1, max_length=128)
    parent_draft_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    change_kind: Literal["DATA_REQUIREMENT_SCOPE_CORRECTION"]
    scope_changes: tuple[ScopeChange, ...] = Field(min_length=1, max_length=3)
    reason: str = Field(min_length=1, max_length=2000)


class ProposalV3(ProposalV2, GroundingDeclaration):
    schema_version: Literal["research_proposal/3"]
    revision: RevisionLink | None


class ReviewDecisionV3(ReviewDecision):
    status: Literal["REJECTED", "BLOCKED_DATA_REQUIREMENT", "BLOCKED_CONTRACT_DEFECT", "AWAITING_OPERATOR_REVIEW"]
    idea_relation: Literal["SAME_RESEARCH_IDEA", "RELATED_VARIANT"]
    attempt_kind: Literal["CORRECTED_REVISION", "NEW_PROPOSAL"]
    parent_draft_id: str | None
    reference_policy: Literal["scoped_registry_references/1"]


class ObjectionV3(ObjectionV2):
    code: Literal["DUPLICATE", "SOURCE_UNSUPPORTED", "TEMPORAL_FAILURE", "INSUFFICIENT_SUPPORT",
                  "COST_UNVERIFIED", "UNSUPPORTED_CLAIM", "MISSING_COUNTEREVIDENCE", "REQUIREMENT_CONTRADICTION",
                  "PRIOR_RELATION_MISMATCH", "EVIDENCE_SCOPE_MISMATCH", "NON_PREDICTIVE_FALSIFIER"]


class CritiqueV3(CritiqueV2):
    schema_version: Literal["research_critique/3"]
    objections: tuple[ObjectionV3, ...] = Field(max_length=10)
    prior_attempt_consistency: Literal["CONSISTENT", "CONTRADICTORY"]
    evidence_attribution: Literal["CONSISTENT", "CONTRADICTORY"]
    falsifier_consistency: Literal["CONSISTENT", "CONTRADICTORY"]
    grounding_explanation: str = Field(min_length=1, max_length=2500)

    @model_validator(mode="after")
    def record_grounding_objections(self):
        for assessment, code in [(self.prior_attempt_consistency, "PRIOR_RELATION_MISMATCH"),
                                 (self.evidence_attribution, "EVIDENCE_SCOPE_MISMATCH"),
                                 (self.falsifier_consistency, "NON_PREDICTIVE_FALSIFIER")]:
            if assessment == "CONTRADICTORY" and not any(
                item.code == code and item.severity != "advisory" for item in self.objections
            ):
                raise ValueError("a grounding contradiction needs its material or blocking objection")
        return self


def grounding_errors(proposal: ProposalV3, context: dict) -> list[str]:
    """Validate typed references only; arbitrary prose still requires review."""
    reasons = []
    signature = digest(proposal.diagnostic)
    expected = {group["signature"] for group in context["prior_groups"]}
    reported = {item.signature for item in proposal.prior_comparisons}
    if expected != reported or len(reported) != len(proposal.prior_comparisons):
        reasons.append("PRIOR_INVENTORY_MISMATCH")
    if any(item.relation != ("SAME_RESEARCH_IDEA" if item.signature == signature else "RELATED_VARIANT")
           for item in proposal.prior_comparisons):
        reasons.append("PRIOR_RELATION_MISMATCH")
    used_evidence = set()
    for claim in proposal.evidence_claims:
        fact = context["facts"].get(claim.fact_id)
        if fact is None:
            reasons.append("UNKNOWN_EVIDENCE_FACT")
            continue
        used_evidence.add(fact["evidence_id"])
        if claim.applies_to == "PROPOSED_CONTRACT" and digest(fact["source_diagnostic"]) != signature:
            reasons.append("EVIDENCE_SCOPE_MISMATCH")
    required = {fact["evidence_id"] for fact in context["facts"].values()}
    if used_evidence != required or set(proposal.evidence_ids) != required:
        reasons.append("EVIDENCE_CITATION_MISMATCH")
    return list(dict.fromkeys(reasons))
