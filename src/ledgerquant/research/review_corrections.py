"""Operator annotations correct interpretation without rewriting old decisions."""

from typing import Literal

from pydantic import Field
from sqlalchemy import select

from . import tables as t
from .registry import RegistryError, append, artifact, now, value
from .types import Record


class ReviewCorrection(Record):
    draft_id: str = Field(min_length=1, max_length=128)
    draft_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    original_review_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    classification: Literal["BLOCKED_CONTRACT_DEFECT", "SAME_IDEA_REVISION_CANDIDATE", "CITATION_NAMESPACE_DEFECT"]
    reason: str = Field(min_length=1, max_length=3000)
    actor: str = Field(min_length=1, max_length=120)


def correct_review(registry, command: ReviewCorrection):
    with registry.engine.begin() as c:
        draft = c.execute(select(t.drafts).where(t.drafts.c.id == command.draft_id)).mappings().one()
        original = c.execute(select(t.run_events.c.detail_id).where(t.run_events.c.run_id == draft["run_id"],
            t.run_events.c.kind == "CONTRACT_REVIEW")).scalar_one()
        if draft["artifact_id"] != command.draft_sha256 or original != command.original_review_sha256:
            raise RegistryError("CORRECTION_IDENTITY_MISMATCH")
        decision = value(c, original)
        if command.classification == "BLOCKED_CONTRACT_DEFECT" and decision["status"] != "BLOCKED_DATA_REQUIREMENT":
            raise RegistryError("CORRECTION_CLASSIFICATION_MISMATCH")
        if command.classification == "SAME_IDEA_REVISION_CANDIDATE" and "DUPLICATE" not in decision["reasons"]:
            raise RegistryError("CORRECTION_CLASSIFICATION_MISMATCH")
        if command.classification == "CITATION_NAMESPACE_DEFECT" and "UNKNOWN_EVIDENCE" not in decision["reasons"]:
            raise RegistryError("CORRECTION_CLASSIFICATION_MISMATCH")
        detail = {**command.model_dump(mode="json"), "original_decision_retained": True,
                  "admission_granted": False, "exposure": "UNCHANGED", "attempt_count": "RETAINED"}
        row = append(c, t.commitments, {"id": f"{draft['id']}:CONTRACT_REVIEW_CORRECTION", "draft_id": draft["id"],
            "kind": "CONTRACT_REVIEW_CORRECTION", "actor": command.actor, "artifact_id": artifact(c, detail), "created_at": now()})
        return {"correction_sha256": row["artifact_id"], **detail}
