"""Rebuildable, run-frozen views of authorized evidence and prior attempts."""

from itertools import combinations

from sqlalchemy import select

from . import tables as t
from .catalog import CATALOG, Diagnostic
from .contract_revisions import RevisionAuthorization, corrected_fields
from .registry import RegistryError, append, artifact, now, value
from .repair_exposure import (REPAIR_POLICIES, TOOL_POLICIES, RepairDenied, assessment, participant_runs,
                              registry_findings, verify_defect_reference)
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


def build_context(connection, manifest, cutoff, exclude_run_id, task=None):
    """The task names authorized parents and the repair policy; the service assesses exposure."""
    c = connection
    task = task or {}
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
        prior_drafts[row["id"]] = {"draft_id": row["id"], "draft_sha256": row["artifact_id"], "proposal": payload,
                                   "run_id": row["run_id"], "signature": row["signature"]}
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
    authorizations = [RevisionAuthorization.model_validate(raw) for raw in task.get("revision_authorizations", ())]
    policy = task.get("repair_policy")
    if authorizations and policy not in REPAIR_POLICIES:
        raise RegistryError("REPAIR_POLICY_REQUIRED")
    if policy is not None and not authorizations:
        raise RegistryError("REPAIR_POLICY_WITHOUT_AUTHORIZATION")
    revision_parents = {}
    for authorization in authorizations:
        parent = prior_drafts.get(authorization.parent_draft_id)
        if parent is None or parent["draft_sha256"] != authorization.parent_draft_sha256:
            raise RegistryError("REVISION_PARENT_NOT_IN_PRIOR_INVENTORY")
        if authorization.parent_draft_id in revision_parents:
            raise RegistryError("DUPLICATE_REVISION_AUTHORIZATION")
        changes = [change.model_dump(mode="json") for change in authorization.scope_changes]
        corrected_fields(parent["proposal"], changes)
        verify_defect_reference(c, parent, parent["run_id"], authorization.defect_reference, cutoff)
        record = {"draft_id": parent["draft_id"], "draft_sha256": parent["draft_sha256"], "proposal": parent["proposal"],
                  "scope_changes": changes, "reason": authorization.reason}
        hours = Diagnostic.model_validate(parent["proposal"]["diagnostic"]).hours_utc
        participants = participant_runs(c, parent["draft_id"], parent["signature"], task.get("related_attempt_ids", ()), exclude_run_id)
        findings = registry_findings(c, manifest, hours, cutoff, participants)
        record["repair_eligibility"] = assessment(policy, record, hours, findings, authorization, cutoff, task.get("submission_policy"))
        revision_parents[authorization.parent_draft_id] = record
    hours = CATALOG["permitted_hours_utc"]
    unused = [list(subset) for size in range(1, len(hours) + 1) for subset in combinations(hours, size)
              if digest(Diagnostic(hours_utc=subset)) not in groups]
    return {"version": "research_grounding/2", "family_id": manifest["family_id"],
            "cutoff_at": cutoff.isoformat(), "prior_groups": [{"signature": key, **item} for key, item in sorted(groups.items())],
            "facts": facts, "unused_catalog_hours": unused,
            "revision_parents": revision_parents,
            "repair_policy": policy, "tool_policy": TOOL_POLICIES.get(policy, "research_tools/1"),
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
            return _enforced(value(c, recorded))
        manifest_id = c.execute(select(t.snapshots.c.manifest_id).where(t.snapshots.c.id == run["snapshot_id"])).scalar_one()
        result = build_context(c, value(c, manifest_id), run["created_at"], run_id, value(c, run["task_id"]))
        append(c, t.run_events, {"id": event_id, "run_id": run_id, "kind": "GROUNDING_CONTEXT",
                               "detail_id": artifact(c, result), "created_at": now()})
    return _enforced(result)


def _enforced(context):
    """A denied strict repair is recorded first, then stops the run before any provider call."""
    denied = [parent for parent in context["revision_parents"].values()
              if parent.get("repair_eligibility", {}).get("decision") == "DENIED"]
    if denied:
        raise RepairDenied("REPAIR_EXPOSURE_DENIED:" + ",".join(sorted({reason for parent in denied
                                                                      for reason in parent["repair_eligibility"]["reasons"]})))
    return context


def recorded_context(connection, run_id):
    key = connection.execute(select(t.run_events.c.detail_id).where(t.run_events.c.id == f"{run_id}:GROUNDING_CONTEXT")).scalar_one_or_none()
    if key is None:
        raise RegistryError("GROUNDING_CONTEXT_REQUIRED")
    return value(connection, key)
