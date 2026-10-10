"""Operator-only decisions and fixed-catalog development, outside agent tools."""

from typing import Literal

from pydantic import Field
from sqlalchemy import select, text

from . import tables as t
from .catalog import CATALOG, develop
from .proposals import review
from .scoped_proposals import parse_proposal, parse_critique
from .grounded_proposals import ProposalV3
from .grounding import recorded_context
from .registry import RegistryError, append, artifact, now, value
from .repair_exposure import POLICY_VERSION, RepairDenied, participant_runs, recheck, registry_findings
from .types import Record, digest


class Admission(Record):
    draft_id: str = Field(min_length=1, max_length=128)
    draft_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    actor: str = Field(min_length=1, max_length=120)
    action: Literal["ADMIT_DEVELOPMENT", "REJECT"]
    reason: str = Field(min_length=1, max_length=3000)
    objection_resolutions: dict[str, str]


def admit(registry, command: Admission):
    denied = None
    with registry.engine.begin() as c:
        draft = c.execute(select(t.drafts).where(t.drafts.c.id == command.draft_id).with_for_update()).mappings().one()
        if draft["artifact_id"] != command.draft_sha256:
            raise RegistryError("DRAFT_HASH_MISMATCH")
        _serialize_family(c, draft["family_id"])
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
        decision = review(proposal, critique, set(manifest["evidence"]), known,
                          recorded_context(c, run["id"]) if isinstance(proposal, ProposalV3) else None)
        if command.action == "ADMIT_DEVELOPMENT" and frozen is None:
            if decision.status != "AWAITING_OPERATOR_REVIEW":
                raise RegistryError("CONTRACT_NOT_ADMISSIBLE")
            required = {str(i) for i, objection in enumerate(critique.objections) if objection.severity != "advisory"}
            if not required <= set(command.objection_resolutions) or any(not text.strip() for text in command.objection_resolutions.values()):
                raise RegistryError("UNRESOLVED_CRITIC_OBJECTION")
        repair = None
        if isinstance(proposal, ProposalV3) and proposal.revision is not None and command.action == "ADMIT_DEVELOPMENT":
            repair = _repair_recheck(c, draft, run, manifest, proposal, command.actor)
        if repair is not None and repair["decision"] == "DENIED":
            # The denial is committed as an append-only record before the command is refused.
            denied = repair
        else:
            if isinstance(proposal, ProposalV3):
                _commit(c, draft["id"], command.actor, "CONTRACT_REVIEW_ASSESSMENT", {
                    "proposal_sha256": draft["artifact_id"], "critique_sha256": critique_id,
                    "decision": decision.model_dump(mode="json")})
            _commit(c, draft["id"], command.actor, "OPERATOR_DECISION", command)
            if command.action == "REJECT":
                return {"status": "REJECTED", "economic_failure": False}
            freeze = value(c, frozen) if frozen else {"proposal_id": draft["artifact_id"], "catalog": CATALOG, "catalog_sha256": digest(CATALOG),
                      "snapshot_id": run["snapshot_id"], "development_id": manifest["development_id"],
                      "family_id": draft["family_id"], "campaign_id": run["campaign_id"],
                      "registered_at": draft["created_at"].isoformat(), "confirmatory_tests": 0,
                      "validation_status": "NO_INDEPENDENT_WINDOW"}
            if isinstance(proposal, ProposalV3) and proposal.revision is not None and not frozen:
                freeze = {**freeze, "revision": proposal.revision.model_dump(mode="json"),
                          "idea_relation": "SAME_RESEARCH_IDEA", "attempt_kind": "CORRECTED_REVISION",
                          "repair_eligibility": _freeze_summary(repair)}
            _commit(c, draft["id"], command.actor, "DESIGN_FREEZE", freeze)
    if denied is not None:
        raise RepairDenied("REPAIR_EXPOSURE_DENIED:" + ",".join(denied["reasons"]))
    # Commit the design before any new development calculation. Re-running the
    # same command resumes the deterministic job, never a new provider call.
    result = develop(proposal.diagnostic, registry.read(manifest["development_id"])["cases"])
    with registry.engine.begin() as c:
        _serialize_family(c, draft["family_id"])
        _commit(c, draft["id"], "catalog:" + CATALOG["version"], "DEVELOPMENT_RESULT", result)
        status = "NO_INDEPENDENT_WINDOW" if result["data_sufficient"] else "INSUFFICIENT_SUPPORT"
        lock = {"design_sha256": digest(freeze), "diagnostic": proposal.diagnostic.model_dump(mode="json"),
                "baseline_class": result["baseline_class"], "development_sha256": digest(result),
                "status": status, "economic_claim": None, "execution_allowed": False}
        _commit(c, draft["id"], "catalog:" + CATALOG["version"], "CANDIDATE_LOCK", lock)
    return lock


def _serialize_family(connection, family_id):
    """Admissions and measured-result commits of one family never interleave, across campaigns."""
    connection.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": "research_family:" + family_id})


def _repair_recheck(connection, draft, run, manifest, proposal, actor):
    """Transactional recheck against intervening exposure; an existing record is never rewritten.

    The recheck, operator decision and design freeze commit together, so a resumed
    development job finds either all of them or none. A result that did not exist when
    the design froze cannot have informed that frozen contract.
    """
    c = connection
    existing = c.execute(select(t.commitments.c.artifact_id).where(t.commitments.c.id == draft["id"] + ":REPAIR_ELIGIBILITY_RECHECK")).scalar_one_or_none()
    if existing:
        return value(c, existing)
    parent_id = proposal.revision.parent_draft_id
    frozen = recorded_context(c, run["id"])["revision_parents"].get(parent_id, {}).get("repair_eligibility")
    if frozen is None:
        return None  # recorded under a grounding contract that predates repair_exposure/1
    cutoff = now()
    participants = participant_runs(c, parent_id, draft["signature"], value(c, run["task_id"]).get("related_attempt_ids", ()), run["id"])
    findings = registry_findings(c, manifest, proposal.diagnostic.hours_utc, cutoff, participants)
    detail = recheck(frozen, findings, cutoff, actor)
    _commit(c, draft["id"], actor, "REPAIR_ELIGIBILITY_RECHECK", detail)
    return detail


def _freeze_summary(repair):
    if repair is None:
        return {"decision": "NOT_ASSESSED", "policy_version": None,
                "reason": "recorded grounding context predates " + POLICY_VERSION}
    return {"decision": repair["decision"], "exposure": repair["exposure"], "policy_version": POLICY_VERSION,
            "recheck_sha256": digest(repair)}


def _commit(connection, draft_id, actor, kind, detail):
    return append(connection, t.commitments, {"id": f"{draft_id}:{kind}", "draft_id": draft_id,
        "actor": actor, "kind": kind, "artifact_id": artifact(connection, detail), "created_at": now()})
