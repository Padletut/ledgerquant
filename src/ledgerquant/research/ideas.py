"""Exploratory ideas are proposals, never evaluator contracts or measurements."""

from typing import Annotated

from pydantic import Field

from .types import Record


ShortText = Annotated[str, Field(min_length=1, max_length=120)]


class Idea(Record):
    title: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=2000)
    instruments: tuple[ShortText, ...] = Field(min_length=1, max_length=16)
    proposed_decision: str = Field(min_length=1, max_length=2000)
    proposed_payoff: str = Field(min_length=1, max_length=2000)
    rationale: str = Field(min_length=1, max_length=3000)
    falsifier: str | None = Field(default=None, min_length=1, max_length=2000)
    source_refs: tuple[ShortText, ...] = Field(default=(), max_length=16)
    related_draft_ids: tuple[ShortText, ...] = Field(default=(), max_length=16)
    measurement_gaps: tuple[str, ...] = Field(default=(), max_length=10)


class IdeaCritique(Record):
    draft_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    summary: str = Field(min_length=1, max_length=3000)
    concerns: tuple[str, ...] = Field(default=(), max_length=10)
    source_refs: tuple[ShortText, ...] = Field(default=(), max_length=16)


def references_allowed(task: object, source_refs: tuple[str, ...], related_draft_ids: tuple[str, ...] = ()) -> bool:
    """Model citations must come from the immutable operator task."""
    if not isinstance(task, dict):
        return False
    sources = task.get("source_refs", ())
    related = task.get("related_draft_ids", ())
    if any(not isinstance(items, (list, tuple)) or not all(isinstance(item, str) for item in items)
           for items in (sources, related)):
        return False
    return set(source_refs) <= set(sources) and set(related_draft_ids) <= set(related)
