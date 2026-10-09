"""Explicit v2 transition; historical v1 artifacts retain their exact identity."""

from typing import Literal

from pydantic import Field, model_validator

from .proposals import Critique, DataRequirement, Objection, Proposal


REQUIREMENT_RULES = """Every v2 data requirement has an explicit scope:
current_diagnostic blocks this attempt when the source is unavailable;
future_economic records a deferred prerequisite and does not block this price
diagnostic or grant economic eligibility. Requiring broker_costs for the current
no-orders, no-economic-claim catalog is REQUIREMENT_CONTRADICTION, a contract
rejection, never a measured COST_FAILURE. Raw news or historical sentiment
required now remains BLOCKED_DATA_REQUIREMENT, pending data and a reviewed
catalog extension. Do not silently execute an unsupported event-conditioned rule.
Check mechanism, support and falsifier against these structured scopes. A claim
to use a source now while deferring its requirement is a narrative contradiction.
Preserve it as a material REQUIREMENT_CONTRADICTION objection for operator review.
"""


class ScopedRequirement(DataRequirement):
    scope: Literal["current_diagnostic", "future_economic"]


class ProposalV2(Proposal):
    schema_version: Literal["research_proposal/2"]
    data_requirements: tuple[ScopedRequirement, ...] = Field(max_length=3)


class ObjectionV2(Objection):
    code: Literal["DUPLICATE", "SOURCE_UNSUPPORTED", "TEMPORAL_FAILURE", "INSUFFICIENT_SUPPORT",
                  "COST_UNVERIFIED", "UNSUPPORTED_CLAIM", "MISSING_COUNTEREVIDENCE", "REQUIREMENT_CONTRADICTION"]


class CritiqueV2(Critique):
    schema_version: Literal["research_critique/2"]
    objections: tuple[ObjectionV2, ...] = Field(max_length=10)
    requirement_consistency: Literal["CONSISTENT", "CONTRADICTORY"]
    requirement_explanation: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def record_contradiction(self):
        if self.requirement_consistency == "CONTRADICTORY" and not any(
            item.code == "REQUIREMENT_CONTRADICTION" and item.severity != "advisory" for item in self.objections
        ):
            raise ValueError("a requirement contradiction needs a material or blocking objection")
        return self


def contract_types(version):
    if version == 1:
        return Proposal, Critique
    if version == 2:
        return ProposalV2, CritiqueV2
    if version == 3:
        from .grounded_proposals import ProposalV3, CritiqueV3
        return ProposalV3, CritiqueV3
    raise ValueError("unsupported research contract version")


def parse_proposal(payload):
    return _parse(payload, "research_proposal", 0)


def parse_critique(payload):
    return _parse(payload, "research_critique", 1)


def _parse(payload, prefix, index):
    if "schema_version" not in payload:
        return contract_types(1)[index].model_validate(payload)
    for version in (2, 3):
        if payload["schema_version"] == f"{prefix}/{version}":
            return contract_types(version)[index].model_validate(payload)
    raise ValueError("unsupported research contract version")
