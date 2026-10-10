"""Exploratory ideas are proposals, never evaluator contracts or measurements."""

from typing import Annotated, Literal

from pydantic import Field
from sqlalchemy import select

from . import tables as t
from .registry import RegistryError, value
from .types import Record


ShortText = Annotated[str, Field(min_length=1, max_length=120)]


class Idea(Record):
    title: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=2000)
    instruments: tuple[ShortText, ...] = Field(min_length=1, max_length=16,
        description="Proposed CFD instrument names; put feeds and features in candidate_information.")
    candidate_information: str | None = Field(default=None, max_length=2000)
    proposed_decision: str = Field(min_length=1, max_length=2000)
    proposed_payoff: str = Field(min_length=1, max_length=2000,
        description="Proposed observable outcome and horizon, with units if known; do not describe the research process.")
    rationale: str = Field(min_length=1, max_length=3000)
    falsifier: str | None = Field(default=None, min_length=1, max_length=2000)
    source_refs: tuple[ShortText, ...] = Field(default=(), max_length=16)
    related_draft_ids: tuple[ShortText, ...] = Field(default=(), max_length=16)
    measurement_gaps: tuple[str, ...] = Field(default=(), max_length=10)


class IdeaPark(Record):
    """An honest end to one exploratory attempt, without a fabricated payoff."""

    kind: Literal["PARKED"] = "PARKED"
    title: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=2000)
    reason: str = Field(min_length=1, max_length=3000)
    revisit_when: str | None = Field(default=None, min_length=1, max_length=1000)
    source_refs: tuple[ShortText, ...] = Field(default=(), max_length=16)
    related_draft_ids: tuple[ShortText, ...] = Field(default=(), max_length=16)


class IdeaCritique(Record):
    draft_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    summary: str = Field(min_length=1, max_length=3000)
    concerns: tuple[str, ...] = Field(default=(), max_length=10)
    source_refs: tuple[ShortText, ...] = Field(default=(), max_length=16)


class IdeaCritiqueV2(IdeaCritique):
    """Model-authored scope checks; labels are not authoritative findings."""

    decision_scope: Literal["MARKET_ACTION", "RESEARCH_PROCESS", "UNCLEAR", "NOT_APPLICABLE"]
    payoff_scope: Literal["ECONOMIC_OUTCOME", "OBSERVABLE_PROXY", "RESEARCH_PROCESS", "UNCLEAR", "NOT_APPLICABLE"]
    exposure_status: Literal["DEVELOPMENT_EXPOSED", "UNVERIFIED", "NO_VALIDATION_CLAIM"]


def references_allowed(task: object, source_refs: tuple[str, ...], related_draft_ids: tuple[str, ...] = ()) -> bool:
    """Allow cited sources and drafts already named by the immutable task."""
    if not isinstance(task, dict):
        return False
    sources = task.get("source_refs", ())
    related = task.get("related_draft_ids", ())
    if any(not isinstance(items, (list, tuple)) or not all(isinstance(item, str) for item in items)
           for items in (sources, related)):
        return False
    permitted_drafts = set(related)
    parent = task.get("parent_idea_draft_id")
    if isinstance(parent, str) and parent:
        permitted_drafts.add(parent)
    return set(source_refs) <= set(sources) and set(related_draft_ids) <= permitted_drafts


def recorded_idea(connection, draft_id: str) -> dict:
    """Resolve an immutable idea and its Critic review by registered workflow."""
    draft = connection.execute(select(t.drafts).where(t.drafts.c.id == draft_id)).mappings().one_or_none()
    if draft is None:
        raise RegistryError("UNKNOWN_IDEA_DRAFT")
    run = connection.execute(select(t.runs).where(t.runs.c.id == draft["run_id"])).mappings().one()
    definition_id = connection.execute(select(t.agent_versions.c.definition_id).where(
        t.agent_versions.c.id == run["research_version"])).scalar_one()
    if value(connection, definition_id).get("workflow") != "idea_exploration":
        raise RegistryError("REFERENCE_IS_NOT_EXPLORATORY_IDEA")
    critique = connection.execute(select(t.critiques).where(t.critiques.c.draft_id == draft_id)).mappings().one_or_none()
    if critique is None:
        raise RegistryError("IDEA_CRITIQUE_REQUIRED")
    return {"draft_id": draft_id, "draft_sha256": draft["artifact_id"], "created_at": draft["created_at"],
            "reviewed_at": critique["created_at"],
            "idea": value(connection, draft["artifact_id"]), "critique_sha256": critique["artifact_id"],
            "critique": value(connection, critique["artifact_id"])}
