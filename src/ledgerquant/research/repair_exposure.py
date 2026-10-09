"""Outcome-exposure assessment for contract repair; the agent never chooses its boundary."""

from datetime import datetime

from sqlalchemy import select

from . import tables as t
from .catalog import Diagnostic
from .contract_revisions import RevisionAuthorization, corrected_fields
from .registry import RegistryError, value
from .types import digest


POLICY_VERSION = "repair_exposure/1"
REPAIR_POLICIES = ("premeasurement_repair", "exposed_corrected_attempt")
TOOL_POLICIES = {"premeasurement_repair": "research_tools/1+outcome_free_repair/1",
                 "exposed_corrected_attempt": "research_tools/1"}
OUTCOME_READS = frozenset({"read_development_snapshot"})
EXPOSURE_ORDER = ("NONE_ESTABLISHED", "UNKNOWN", "EXPOSED")


class RepairDenied(RegistryError):
    """A strict premeasurement repair cannot proceed; the attempt still counts."""


def overlapping(hours, other):
    return bool(set(hours) & set(other))


def labelled_overlap(cases, hours):
    """Labelled cases whose anchor hour belongs to the repaired diagnostic."""
    return sum(1 for case in cases if case.get("target") is not None
               and datetime.fromisoformat(case["anchor_utc"]).hour in hours)


def finding(kind, subject, sha256, observed_at, relevance, **detail):
    return {"kind": kind, "subject": subject, "artifact_sha256": sha256,
            "observed_at": observed_at, "relevance": relevance, **detail}


def registry_exposure(findings):
    relevances = {item["relevance"] for item in findings}
    return "EXPOSED" if "OVERLAPPING" in relevances else "UNKNOWN" if "UNKNOWN" in relevances else "NONE_ESTABLISHED"


def combined_exposure(registry_state, declared):
    """A declared reviewer exposure is never cleared by an empty registry scan."""
    declared_state = {"NONE_DECLARED": "NONE_ESTABLISHED"}.get(declared, declared)
    return max(registry_state, declared_state, key=EXPOSURE_ORDER.index)


def participant_runs(connection, parent_draft_id, signature, related_ids, current_run_id):
    """Parent, same-idea attempts, operator-listed related attempts and this run."""
    c = connection
    runs = {current_run_id}
    for row in c.execute(select(t.drafts).where((t.drafts.c.id == parent_draft_id) | (t.drafts.c.signature == signature))).mappings():
        runs.add(row["run_id"])
    for identity in related_ids:
        draft_run = c.execute(select(t.drafts.c.run_id).where(t.drafts.c.id == identity)).scalar_one_or_none()
        runs.add(draft_run or identity)
    return sorted(runs)


def registry_findings(connection, manifest, hours, cutoff, participants):
    """Every recorded outcome bearing on these hours; absence of rows proves nothing."""
    c = connection
    findings = []
    for evidence_id in sorted(manifest["evidence"]):
        row = c.execute(select(t.evidence).where(t.evidence.c.id == evidence_id)).mappings().one()
        contract = value(c, row["contract_id"])
        source_hours = contract["decision_contract"]["candidate_event_rule"]["hours_utc"]
        findings.append(finding("RELEASED_EVIDENCE", evidence_id, row["artifact_id"], row["original_registered_at"].isoformat(),
            "OVERLAPPING" if overlapping(hours, source_hours) else "UNRELATED", hours_utc=list(source_hours),
            windows=[{key: window[key] for key in ("start_inclusive_utc", "end_exclusive_utc")} for window in contract["validation_windows"]]))
    drafts = c.execute(select(t.drafts).where(t.drafts.c.family_id == manifest["family_id"], t.drafts.c.created_at <= cutoff)
                       .order_by(t.drafts.c.created_at, t.drafts.c.id)).mappings().all()
    for draft in drafts:
        try:
            draft_hours = Diagnostic.model_validate(value(c, draft["artifact_id"])["diagnostic"]).hours_utc
        except (ValueError, KeyError, TypeError):
            findings.append(finding("DRAFT_DIAGNOSTIC", draft["id"], draft["artifact_id"], draft["created_at"].isoformat(), "UNKNOWN"))
            continue
        relevance = "OVERLAPPING" if overlapping(hours, draft_hours) else "UNRELATED"
        measured = c.execute(select(t.commitments).where(t.commitments.c.draft_id == draft["id"],
            t.commitments.c.kind.in_(("DEVELOPMENT_RESULT", "CANDIDATE_LOCK")), t.commitments.c.created_at <= cutoff)
            .order_by(t.commitments.c.created_at)).mappings()
        for row in measured:
            findings.append(finding(row["kind"], draft["id"], row["artifact_id"], row["created_at"].isoformat(), relevance,
                                    hours_utc=list(draft_hours)))
    for run_id in participants:
        if c.execute(select(t.runs.c.id).where(t.runs.c.id == run_id)).scalar_one_or_none() is None:
            findings.append(finding("PARTICIPANT_RUN", run_id, None, None, "UNKNOWN"))
            continue
        reads = c.execute(select(t.tool_calls).where(t.tool_calls.c.run_id == run_id, t.tool_calls.c.name.in_(OUTCOME_READS),
            t.tool_calls.c.created_at <= cutoff).order_by(t.tool_calls.c.created_at, t.tool_calls.c.id)).mappings()
        for row in reads:
            result = value(c, row["result_id"])
            if "error" in result:
                continue
            cases = result.get("cases")
            if not isinstance(cases, list):
                findings.append(finding("LABELLED_CASE_READ", run_id, row["result_id"], row["created_at"].isoformat(), "UNKNOWN", role=row["role"]))
                continue
            labelled = labelled_overlap(cases, hours)
            findings.append(finding("LABELLED_CASE_READ", run_id, row["result_id"], row["created_at"].isoformat(),
                "OVERLAPPING" if labelled else "UNRELATED", role=row["role"], cases_read=len(cases), labelled_overlapping_cases=labelled))
    return findings


def verify_defect_reference(connection, parent, parent_run_id, reference, cutoff):
    """The authorized patch must repair a defect somebody already reviewed and recorded."""
    c = connection
    if reference.kind == "CONTRACT_REVIEW_CORRECTION":
        row = c.execute(select(t.commitments).where(t.commitments.c.id == f"{parent['draft_id']}:CONTRACT_REVIEW_CORRECTION",
                                                    t.commitments.c.created_at <= cutoff)).mappings().one_or_none()
        recorded = value(c, row["artifact_id"]).get("classification") if row and row["artifact_id"] == reference.sha256 else None
    else:
        row = c.execute(select(t.run_events).where(t.run_events.c.id == f"{parent_run_id}:CONTRACT_REVIEW",
                                                   t.run_events.c.created_at <= cutoff)).mappings().one_or_none()
        recorded = value(c, row["detail_id"]).get("status") if row and row["detail_id"] == reference.sha256 else None
    if recorded != reference.classification:
        raise RegistryError("DEFECT_REFERENCE_INVALID")


def assessment(policy, parent, hours, findings, authorization: RevisionAuthorization, cutoff, submission_policy):
    """Versioned repair-eligibility record; EXPOSED or UNKNOWN denies the strict route only."""
    registry_state = registry_exposure(findings)
    exposure = combined_exposure(registry_state, authorization.reviewer_outcome_exposure)
    reasons = []
    if exposure == "EXPOSED":
        reasons.append("RELEVANT_OUTCOME_EXPOSED")
    elif exposure == "UNKNOWN":
        reasons.append("EXPOSURE_UNKNOWN")
    if authorization.reviewer_outcome_exposure != "NONE_DECLARED":
        reasons.append("REVIEWER_EXPOSURE_" + authorization.reviewer_outcome_exposure)
    if policy == "premeasurement_repair" and submission_policy != "revision_only":
        reasons.append("REVISION_ONLY_REQUIRED")
    if policy == "premeasurement_repair":
        decision = "DENIED" if reasons else "ELIGIBLE_PREMEASUREMENT_REPAIR"
    else:
        decision = "EXPOSED_CORRECTED_ATTEMPT"
    requirements = parent["proposal"]["data_requirements"]
    diff = [{"requirement_index": change["requirement_index"], "source": requirements[change["requirement_index"]]["source"],
             "before": requirements[change["requirement_index"]].get("scope", "current_diagnostic"), "after": change["scope"]}
            for change in parent["scope_changes"]]
    return {"version": POLICY_VERSION, "stage": "AUTHORIZATION", "repair_policy": policy, "tool_policy": TOOL_POLICIES[policy],
            "parent_draft_id": parent["draft_id"], "parent_draft_sha256": parent["draft_sha256"],
            "corrected_contract_sha256": digest(corrected_fields(parent["proposal"], parent["scope_changes"])),
            "authorized_patch": parent["scope_changes"], "substantive_diff": diff,
            "defect_reference": authorization.defect_reference.model_dump(mode="json"),
            "diagnostic_hours_utc": list(hours), "assessed_cutoff_at": cutoff.isoformat(),
            "reviewer": authorization.reviewer, "reviewer_outcome_exposure": authorization.reviewer_outcome_exposure,
            "model_knowledge": "UNASSESSED_SEPARATE_FACT", "findings": findings,
            "registry_exposure": registry_state, "exposure": exposure, "decision": decision, "reasons": reasons}


def recheck(frozen, findings, cutoff, reviewer):
    """Admission recheck against intervening exposure; a denial can never be lifted."""
    exposure = combined_exposure(registry_exposure(findings), frozen["reviewer_outcome_exposure"])
    intervening = [item for item in findings if item not in frozen["findings"]]
    reasons = []
    if frozen["decision"] == "DENIED":
        reasons.append("AUTHORIZATION_DENIED")
    if exposure == "EXPOSED":
        reasons.append("RELEVANT_OUTCOME_EXPOSED")
    elif exposure == "UNKNOWN":
        reasons.append("EXPOSURE_UNKNOWN")
    if frozen["repair_policy"] == "premeasurement_repair":
        decision = "DENIED" if reasons else "ELIGIBLE_PREMEASUREMENT_REPAIR"
    else:
        decision = "EXPOSED_CORRECTED_ATTEMPT"
    return {"version": POLICY_VERSION, "stage": "ADMISSION_RECHECK", "repair_policy": frozen["repair_policy"],
            "authorization_sha256": digest(frozen), "authorization_decision": frozen["decision"],
            "parent_draft_id": frozen["parent_draft_id"], "assessed_cutoff_at": cutoff.isoformat(), "reviewer": reviewer,
            "findings": findings, "intervening_findings": intervening, "exposure": exposure,
            "decision": decision, "reasons": reasons}

