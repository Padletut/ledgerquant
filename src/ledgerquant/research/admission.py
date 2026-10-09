"""Operator-only decisions and fixed-catalog development, outside agent tools."""

from typing import Literal

from pydantic import Field
from sqlalchemy import select

from . import tables as t
from .catalog import CATALOG, develop
from .proposals import review
from .scoped_proposals import parse_proposal, parse_critique
from .registry import RegistryError, append, artifact, now, value
from .types import Record, digest


class Admission(Record):
    draft_id: str = Field(min_length=1, max_length=128)
    draft_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    actor: str = Field(min_length=1, max_length=120)
    action: Literal["ADMIT_DEVELOPMENT", "REJECT"]
    reason: str = Field(min_length=1, max_length=3000)
    objection_resolutions: dict[str, str]


def admit(registry, command: Admission):
    with registry.engine.begin() as c:
        draft = c.execute(select(t.drafts).where(t.drafts.c.id == command.draft_id).with_for_update()).mappings().one()
        if draft["artifact_id"] != command.draft_sha256:
            raise RegistryError("DRAFT_HASH_MISMATCH")
        run = c.execute(select(t.runs).where(t.runs.c.id == draft["run_id"])).mappings().one()
        snapshot = c.execute(select(t.snapshots.c.manifest_id).where(t.snapshots.c.id == run["snapshot_id"])).scalar_one()
        manifest = value(c, snapshot)
        invalid = set(c.execute(select(t.evidence_events.c.evidence_id).where(t.evidence_events.c.kind == "INVALIDATED")).scalars())
        if invalid & set(manifest["evidence"]):
            raise RegistryError("SOURCE_REVIEW_REQUIRED")
        prior = c.execute(select(t.commitments).where(t.commitments.c.id == draft["id"] + ":OPERATOR_DECISION")).mappings().one_or_none()
        if prior and prior["artifact_id"] != digest(command):
            raise RegistryError("operator command conflicts with the recorded decision")
        locked = c.execute(select(t.commitments.c.artifact_id).where(t.commitments.c.id == draft["id"] + ":CANDIDATE_LOCK")).scalar_one_or_none()
        if prior and locked:
            return value(c, locked)
        frozen = c.execute(select(t.commitments.c.artifact_id).where(t.commitments.c.id == draft["id"] + ":DESIGN_FREEZE")).scalar_one_or_none()
        proposal = parse_proposal(value(c, draft["artifact_id"]))
        critique_id = c.execute(select(t.critiques.c.artifact_id).where(t.critiques.c.draft_id == draft["id"])).scalar_one()
        critique = parse_critique(value(c, critique_id))
        known = set(c.execute(select(t.drafts.c.signature).where(t.drafts.c.id != draft["id"])).scalars())
        decision = review(proposal, critique, set(manifest["evidence"]), known)
        if command.action == "ADMIT_DEVELOPMENT" and frozen is None:
            if decision.status != "AWAITING_OPERATOR_REVIEW":
                raise RegistryError("CONTRACT_NOT_ADMISSIBLE")
            required = {str(i) for i, objection in enumerate(critique.objections) if objection.severity != "advisory"}
            if not required <= set(command.objection_resolutions) or any(not text.strip() for text in command.objection_resolutions.values()):
                raise RegistryError("UNRESOLVED_CRITIC_OBJECTION")
        _commit(c, draft["id"], command.actor, "OPERATOR_DECISION", command)
        if command.action == "REJECT":
            return {"status": "REJECTED", "economic_failure": False}
        freeze = value(c, frozen) if frozen else {"proposal_id": draft["artifact_id"], "catalog": CATALOG, "catalog_sha256": digest(CATALOG),
                  "snapshot_id": run["snapshot_id"], "development_id": manifest["development_id"],
                  "family_id": draft["family_id"], "campaign_id": run["campaign_id"],
                  "registered_at": draft["created_at"].isoformat(), "confirmatory_tests": 0,
                  "validation_status": "NO_INDEPENDENT_WINDOW"}
        _commit(c, draft["id"], command.actor, "DESIGN_FREEZE", freeze)
    # Commit the design before any new development calculation. Re-running the
    # same command resumes the deterministic job, never a new provider call.
    result = develop(proposal.diagnostic, registry.read(manifest["development_id"])["cases"])
    with registry.engine.begin() as c:
        _commit(c, draft["id"], "catalog:" + CATALOG["version"], "DEVELOPMENT_RESULT", result)
        status = "NO_INDEPENDENT_WINDOW" if result["data_sufficient"] else "INSUFFICIENT_SUPPORT"
        lock = {"design_sha256": digest(freeze), "diagnostic": proposal.diagnostic.model_dump(mode="json"),
                "baseline_class": result["baseline_class"], "development_sha256": digest(result),
                "status": status, "economic_claim": None, "execution_allowed": False}
        _commit(c, draft["id"], "catalog:" + CATALOG["version"], "CANDIDATE_LOCK", lock)
    return lock


def _commit(connection, draft_id, actor, kind, detail):
    return append(connection, t.commitments, {"id": f"{draft_id}:{kind}", "draft_id": draft_id,
        "actor": actor, "kind": kind, "artifact_id": artifact(connection, detail), "created_at": now()})
