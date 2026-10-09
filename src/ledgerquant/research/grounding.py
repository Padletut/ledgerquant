"""Rebuildable, run-frozen views of authorized evidence and prior attempts."""

from itertools import combinations

from sqlalchemy import select

from . import tables as t
from .catalog import CATALOG, Diagnostic
from .contract_revisions import RevisionAuthorization, corrected_fields
from .registry import RegistryError, append, artifact, now, value
from .types import digest


METRICS = ("gate_decision", "validation.candidate_accuracy", "validation.baseline_accuracy",
           "validation.paired_accuracy_difference")


def evidence_view(evidence_id, evidence_hash, evidence, contract):
    """Project only supported diagnostic fields, never broker credentials/paths."""
    decision = contract["decision_contract"]
    diagnostic = Diagnostic(hours_utc=decision["candidate_event_rule"]["hours_utc"],
        instrument=decision["instrument"], candidate_rule=decision["candidate_rule"],
        orders_allowed=decision["orders_allowed"], lookback_seconds=contract["feature_contract"]["lookback_seconds"],
        horizon_seconds=contract["payoff_contract"]["settlement_horizon_seconds"]).model_dump(mode="json")
    facts = {}
    for field in METRICS:
        measured = evidence
        for key in field.split("."):
            measured = measured[key]
        fact = {"evidence_id": evidence_id, "evidence_sha256": evidence_hash,
                "contract_sha256": evidence["contract_sha256"], "source_diagnostic": diagnostic,
                "validation_windows": [{key: window[key] for key in ("start_inclusive_utc", "end_exclusive_utc")}
                                       for window in contract["validation_windows"]],
                "baseline": contract["payoff_contract"]["baseline"], "evidence_mode": evidence["evidence_mode"],
                "economic_claim": evidence["economic_claim"], "field": field, "value": measured}
        facts[digest(fact)] = fact
    return diagnostic, facts


def build_context(connection, manifest, cutoff, exclude_run_id, revision_authorizations=()):
    c = connection
    invalid = set(c.execute(select(t.evidence_events.c.evidence_id).where(t.evidence_events.c.kind == "INVALIDATED")).scalars())
    if invalid & set(manifest["evidence"]):
        raise RegistryError("SOURCE_REVIEW_REQUIRED")
    groups, facts = {}, {}
    for evidence_id, expected_hash in sorted(manifest["evidence"].items()):
        row = c.execute(select(t.evidence).where(t.evidence.c.id == evidence_id)).mappings().one()
        evidence = value(c, row["artifact_id"])
        if row["artifact_id"] != expected_hash or row["contract_id"] != evidence["contract_sha256"]:
            raise RegistryError("EVIDENCE_LINEAGE_MISMATCH")
        diagnostic, projected = evidence_view(evidence_id, expected_hash, evidence, value(c, row["contract_id"]))
        facts.update(projected)
        group = groups.setdefault(digest(diagnostic), {"diagnostic": diagnostic, "attempts": []})
        group["attempts"].append({"id": evidence_id, "artifact_sha256": expected_hash,
                                  "kind": "released_evaluation", "status": evidence["gate_decision"]})
    query = select(t.drafts).where(t.drafts.c.family_id == manifest["family_id"],
                                   t.drafts.c.created_at <= cutoff, t.drafts.c.run_id != exclude_run_id).order_by(t.drafts.c.created_at, t.drafts.c.id)
    prior_drafts = {}
    for row in c.execute(query).mappings():
        payload = value(c, row["artifact_id"])
        prior_drafts[row["id"]] = {"draft_id": row["id"], "draft_sha256": row["artifact_id"], "proposal": payload}
        diagnostic = Diagnostic.model_validate(payload["diagnostic"]).model_dump(mode="json")
        if digest(diagnostic) != row["signature"]:
            raise RegistryError("DRAFT_SIGNATURE_MISMATCH")
        status_id = c.execute(select(t.run_events.c.detail_id).where(t.run_events.c.run_id == row["run_id"],
            t.run_events.c.kind == "CONTRACT_REVIEW", t.run_events.c.created_at <= cutoff)).scalar_one_or_none()
        status = value(c, status_id).get("status", "UNKNOWN") if status_id else "PROPOSED"
        correction = c.execute(select(t.commitments.c.artifact_id).where(t.commitments.c.draft_id == row["id"],
            t.commitments.c.kind == "CONTRACT_REVIEW_CORRECTION", t.commitments.c.created_at <= cutoff)).scalar_one_or_none()
        classification = value(c, correction)["classification"] if correction else None
        commitments = {item.kind: item.artifact_id for item in c.execute(select(t.commitments).where(
            t.commitments.c.draft_id == row["id"], t.commitments.c.created_at <= cutoff))}
        effective_status = classification or status
        if "CONTRACT_REVIEW_ASSESSMENT" in commitments:
            effective_status = value(c, commitments["CONTRACT_REVIEW_ASSESSMENT"])["decision"]["status"]
        if "OPERATOR_DECISION" in commitments:
            action = value(c, commitments["OPERATOR_DECISION"])["action"]
            effective_status = "REJECTED" if action == "REJECT" else "ADMITTED_DEVELOPMENT"
        if "CANDIDATE_LOCK" in commitments:
            effective_status = value(c, commitments["CANDIDATE_LOCK"])["status"]
        group = groups.setdefault(row["signature"], {"diagnostic": diagnostic, "attempts": []})
        group["attempts"].append({"id": row["id"], "artifact_sha256": row["artifact_id"],
                                  "kind": "draft", "status": effective_status, "original_contract_status": status,
                                  "later_classification": classification, "commitment_refs": commitments})
    revision_parents = {}
    for raw in revision_authorizations:
        authorization = RevisionAuthorization.model_validate(raw)
        parent = prior_drafts.get(authorization.parent_draft_id)
        if parent is None or parent["draft_sha256"] != authorization.parent_draft_sha256:
            raise RegistryError("REVISION_PARENT_NOT_IN_PRIOR_INVENTORY")
        if authorization.parent_draft_id in revision_parents:
            raise RegistryError("DUPLICATE_REVISION_AUTHORIZATION")
        changes = [change.model_dump(mode="json") for change in authorization.scope_changes]
        corrected_fields(parent["proposal"], changes)
        revision_parents[authorization.parent_draft_id] = {**parent, "scope_changes": changes, "reason": authorization.reason}
    hours = CATALOG["permitted_hours_utc"]
    unused = [list(subset) for size in range(1, len(hours) + 1) for subset in combinations(hours, size)
              if digest(Diagnostic(hours_utc=subset)) not in groups]
    return {"version": "research_grounding/1", "family_id": manifest["family_id"],
            "cutoff_at": cutoff.isoformat(), "prior_groups": [{"signature": key, **item} for key, item in sorted(groups.items())],
            "facts": facts, "unused_catalog_hours": unused,
            "revision_parents": revision_parents,
            "exposure": "RELATED_EXPOSED; all historical validation windows consumed",
            "independence": "Repeated drafts and facts from one evidence artifact are not independent measurements."}


def frozen_context(registry, run_id):
    """Both roles reuse one audited view; the current draft is never its own prior."""
    with registry.engine.begin() as c:
        run = c.execute(select(t.runs).where(t.runs.c.id == run_id)).mappings().one()
        c.execute(select(t.campaigns.c.id).where(t.campaigns.c.id == run["campaign_id"]).with_for_update()).one()
        event_id = f"{run_id}:GROUNDING_CONTEXT"
        recorded = c.execute(select(t.run_events.c.detail_id).where(t.run_events.c.id == event_id)).scalar_one_or_none()
        if recorded:
            return value(c, recorded)
        manifest_id = c.execute(select(t.snapshots.c.manifest_id).where(t.snapshots.c.id == run["snapshot_id"])).scalar_one()
        task = value(c, run["task_id"])
        result = build_context(c, value(c, manifest_id), run["created_at"], run_id, task.get("revision_authorizations", ()))
        append(c, t.run_events, {"id": event_id, "run_id": run_id, "kind": "GROUNDING_CONTEXT",
                               "detail_id": artifact(c, result), "created_at": now()})
        return result


def recorded_context(connection, run_id):
    key = connection.execute(select(t.run_events.c.detail_id).where(t.run_events.c.id == f"{run_id}:GROUNDING_CONTEXT")).scalar_one_or_none()
    if key is None:
        raise RegistryError("GROUNDING_CONTEXT_REQUIRED")
    return value(connection, key)
