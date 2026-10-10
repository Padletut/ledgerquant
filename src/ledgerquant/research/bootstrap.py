"""Operator-owned registration and legacy import; unavailable as an agent tool."""

from datetime import datetime

from sqlalchemy import select

from ledgerquant.agents.definitions import CampaignPolicy, definition
from ledgerquant.models.generation import ModelProfile

from . import tables as t
from .catalog import CATALOG, FAMILY_ID
from .registry import append, artifact, now, RegistryError
from .types import digest


def bootstrap(registry, bundle, profile: ModelProfile, policy: CampaignPolicy, campaign_id: str, workflow="discovery", contract_version=1):
    """Register bounded agents; diagnostic workflows also import prior evidence."""
    if workflow == "idea_exploration" and contract_version != 1:
        raise ValueError("idea exploration uses contract version 1")
    if workflow != "idea_exploration" and bundle is None:
        raise ValueError("legacy evidence bundle required for the diagnostic workflow")
    with registry.engine.begin() as c:
        if workflow == "idea_exploration":
            manifest = {"workflow": workflow, "evidence": {}}
        else:
            for item, attempt, window in zip(bundle["evidence"], bundle["attempts"], bundle["windows"], strict=True):
                content_id = artifact(c, item["original"], raw=True)
                contract_id = artifact(c, attempt["contract"], raw=True)
                if content_id != item["sha256"] or contract_id != attempt["contract_sha256"]:
                    raise RegistryError("import bytes changed")
                append(c, t.evidence, {"id": item["id"], "artifact_id": content_id, "contract_id": contract_id,
                                       "family_id": FAMILY_ID, "original_registered_at": datetime.fromisoformat(attempt["registered_at"]), "created_at": now()})
                append(c, t.windows, {"id": item["id"], "evidence_id": item["id"], "start_at": datetime.fromisoformat(window["start"]),
                                      "end_at": datetime.fromisoformat(window["end"]), "state": "CONSUMED", "created_at": now()})
            manifest = {"catalog": CATALOG, "source": bundle["source"],
                        "development_id": artifact(c, bundle["development"]),
                        "evidence": {item["id"]: item["sha256"] for item in bundle["evidence"]},
                        "historical_attempt_count": len(bundle["evidence"]), "family_id": FAMILY_ID,
                        "windows": bundle["windows"], "ancestry": [{"id": item["id"], "parent_id": item["parent_id"],
                            "relation": "RELATED_EXPOSED"} for item in bundle["attempts"]]}
        snapshot_id = digest(manifest)
        append(c, t.snapshots, {"id": snapshot_id, "manifest_id": artifact(c, manifest), "created_at": now()})
        versions = {}
        for role in ("research", "critic"):
            spec = definition(role, profile, workflow, contract_version)
            versions[role] = digest(spec)
            append(c, t.agent_versions, {"id": versions[role], "role": role, "definition_id": artifact(c, spec), "created_at": now()})
        append(c, t.campaigns, {"id": campaign_id, "policy_id": artifact(c, policy), "created_at": now()})
    return {"campaign_id": campaign_id, "snapshot_id": snapshot_id, "versions": versions,
            "contract_version": contract_version, **({"workflow": workflow} if workflow == "idea_exploration" else {})}


def invalidate_evidence(registry, evidence_id: str, reason: str, actor: str):
    if not reason.strip() or not actor.strip():
        raise RegistryError("correction requires reason and operator")
    with registry.engine.begin() as c:
        if c.execute(select(t.evidence.c.id).where(t.evidence.c.id == evidence_id)).scalar_one_or_none() is None:
            raise RegistryError("unknown evidence")
        detail = {"evidence_id": evidence_id, "reason": reason, "actor": actor, "dependent_support": "REVIEW_REQUIRED"}
        append(c, t.evidence_events, {"id": digest(detail), "evidence_id": evidence_id, "kind": "INVALIDATED",
                                      "detail_id": artifact(c, detail), "created_at": now()})
