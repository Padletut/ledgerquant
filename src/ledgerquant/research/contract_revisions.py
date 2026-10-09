"""Apply an operator-authorized scope patch without redefining the market idea."""

from pydantic import Field

from .grounded_proposals import GroundingDeclaration, ProposalV3, RevisionLink, ScopeChange
from .proposals import Proposal
from .types import Record, digest


class RevisionAuthorization(Record):
    parent_draft_id: str = Field(min_length=1, max_length=128)
    parent_draft_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    scope_changes: tuple[ScopeChange, ...] = Field(min_length=1, max_length=3)
    reason: str = Field(min_length=1, max_length=2000)


class RevisionSubmission(GroundingDeclaration):
    parent_draft_id: str = Field(min_length=1, max_length=128)
    parent_draft_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason: str = Field(min_length=1, max_length=2000)
    admissibility_probability: float = Field(ge=0, le=1, allow_inf_nan=False)


def corrected_fields(parent, changes):
    """Only cost scope changes; new ex-ante belief is attempt metadata."""
    fields = {key: parent[key] for key in Proposal.model_fields}
    requirements = [{**item, "scope": item.get("scope", "current_diagnostic")} for item in parent["data_requirements"]]
    seen = set()
    for raw in changes:
        change = ScopeChange.model_validate(raw)
        index = change.requirement_index
        if index in seen or index >= len(requirements):
            raise ValueError("INVALID_REVISION_PATCH")
        seen.add(index)
        item = requirements[index]
        if item["source"] != "broker_costs" or item["scope"] == change.scope:
            raise ValueError("REVISION_NOT_A_COST_SCOPE_CORRECTION")
        requirements[index] = {**item, "scope": change.scope}
    fields["data_requirements"] = requirements
    return fields


def resolve_revision(submission: RevisionSubmission, context):
    parent = context.get("revision_parents", {}).get(submission.parent_draft_id)
    if parent is None:
        raise ValueError("REVISION_NOT_AUTHORIZED")
    if parent["draft_sha256"] != submission.parent_draft_sha256 or digest(parent["proposal"]) != submission.parent_draft_sha256:
        raise ValueError("REVISION_PARENT_HASH_MISMATCH")
    fields = corrected_fields(parent["proposal"], parent["scope_changes"])
    fields["admissibility_probability"] = submission.admissibility_probability
    grounding = {key: getattr(submission, key) for key in GroundingDeclaration.model_fields}
    return ProposalV3(**fields, **grounding, schema_version="research_proposal/3",
        revision=RevisionLink(parent_draft_id=submission.parent_draft_id, parent_draft_sha256=submission.parent_draft_sha256,
            change_kind="DATA_REQUIREMENT_SCOPE_CORRECTION", scope_changes=parent["scope_changes"], reason=submission.reason))


def revision_errors(proposal: ProposalV3, context):
    link = proposal.revision
    if link is None:
        return []
    parent = context.get("revision_parents", {}).get(link.parent_draft_id)
    if parent is None:
        return ["REVISION_NOT_AUTHORIZED"]
    if parent["draft_sha256"] != link.parent_draft_sha256 or digest(parent["proposal"]) != link.parent_draft_sha256:
        return ["REVISION_PARENT_HASH_MISMATCH"]
    if [item.model_dump(mode="json") for item in link.scope_changes] != parent["scope_changes"]:
        return ["REVISION_PATCH_MISMATCH"]
    expected = corrected_fields(parent["proposal"], parent["scope_changes"])
    expected["admissibility_probability"] = proposal.admissibility_probability
    actual = proposal.model_dump(mode="json")
    if any(actual[key] != expected[key] for key in expected):
        return ["REVISION_CHANGED_OTHER_FIELDS"]
    return []
