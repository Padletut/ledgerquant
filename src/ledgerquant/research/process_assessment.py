"""Reviewed process assessments of one recorded action, sealed from later outcomes."""

import re
from typing import Literal

from pydantic import Field, model_validator
from sqlalchemy import select

from . import tables as t
from .grounded_proposals import ProposalV3
from .proposals import review
from .registry import RegistryError, append, artifact, now, value
from .scoped_proposals import ProposalV2, contract_types, parse_critique, parse_proposal
from .types import Record, digest


ASSESSMENT_VERSION = "process_assessment/1"
PACKET_VERSION = "sealed_process_packet/1"
RUBRIC_VERSION = "process_rubric/1"
DEFECT_CODES = Literal["REQUIREMENT_SCOPE_CONFUSION", "EVIDENCE_MISATTRIBUTION", "DUPLICATE_LINEAGE_ERROR",
                       "NON_PREDICTIVE_FALSIFIER", "OMITTED_CONTRARY_EVIDENCE", "UNSUPPORTED_CAUSAL_CLAIM",
                       "STATUS_MISINTERPRETATION"]
COMPONENTS = Literal["research", "critic", "contract_service", "test_harness", "reference_reviewer", "unknown"]
AGENT_COMPONENTS = {"research", "critic"}
ACTION_ROOTS = ("draft", "critique", "tool_results", "grounding_context")
PACKET_ROOTS = ACTION_ROOTS + ("task", "agent_definition", "recorded_contract_review", "current_service_checks", "test_basis")
DISPUTED_SERVICE_OUTPUT = {"CITATION_NAMESPACE_DEFECT"}
EXCLUDED_FROM_PACKET = ("OPERATOR_DECISION", "DESIGN_FREEZE", "DEVELOPMENT_RESULT", "CANDIDATE_LOCK",
                        "CONTRACT_REVIEW_ASSESSMENT", "REPAIR_ELIGIBILITY_RECHECK", "later drafts", "later evidence")
HEX64 = re.compile(r"^[a-f0-9]{64}$")


class Finding(Record):
    code: DEFECT_CODES
    status: Literal["SUPPORTED", "NOT_SUPPORTED", "UNRESOLVED"]
    responsible_component: COMPONENTS
    severity: Literal["blocking", "material", "advisory"]
    references: tuple[str, ...] = Field(min_length=1, max_length=8)
    applicability: str = Field(min_length=1, max_length=1000)
    explanation: str = Field(min_length=1, max_length=2000)


class CriticDelta(Record):
    """Links a critic-role finding to the research-role finding it missed, introduced or confirmed."""
    code: DEFECT_CODES
    research_assessment_id: str = Field(min_length=1, max_length=128)
    effect: Literal["MISSED", "INTRODUCED", "RESCUED", "CONFIRMED"]


class ProcessAssessment(Record):
    run_id: str = Field(min_length=1, max_length=128)
    role: Literal["research", "critic"]
    draft_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    critique_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    packet_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    rubric_version: Literal["process_rubric/1"]
    assessment_mode: Literal["RETROSPECTIVE_SEALED_PACKET"]
    assessor: str = Field(min_length=1, max_length=120)
    assessor_outcome_exposure: Literal["NONE_DECLARED", "EXPOSED", "UNKNOWN"]
    review_state: Literal["PROPOSED", "REVIEWED"]
    reviewer: str | None = Field(default=None, min_length=1, max_length=120)
    findings: tuple[Finding, ...] = Field(max_length=12)
    limitations: tuple[str, ...] = Field(max_length=8)
    critic_delta: tuple[CriticDelta, ...] = Field(default=(), max_length=12)
    supersedes: str | None = Field(default=None, min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def reviewed_needs_reviewer(self):
        if self.review_state == "REVIEWED" and not self.reviewer:
            raise ValueError("a reviewed assessment names its reviewer")
        if self.role == "research" and self.critic_delta:
            raise ValueError("critic deltas belong to critic-role assessments")
        return self


def neutral_critique(proposal):
    """Deterministic placeholder so draft checks can run before any critique exists."""
    version = 3 if isinstance(proposal, ProposalV3) else 2 if isinstance(proposal, ProposalV2) else 1
    critique_type = contract_types(version)[1]
    extra = {}
    if version >= 2:
        extra.update(schema_version=f"research_critique/{version}", requirement_consistency="CONSISTENT",
                     requirement_explanation="Placeholder for draft-only service checks.")
    if version == 3:
        extra.update(prior_attempt_consistency="CONSISTENT", evidence_attribution="CONSISTENT",
                     falsifier_consistency="CONSISTENT", grounding_explanation="Placeholder for draft-only service checks.")
    return critique_type(draft_sha256=digest(proposal), disposition="REVIEW", objections=(),
                         summary="Service placeholder; not a Critic action.", **extra)


def sealed_packet(connection, run_id, role):
    """Only what the role could see at its action, plus recorded knowledge about the test basis."""
    c = connection
    run = c.execute(select(t.runs).where(t.runs.c.id == run_id)).mappings().one_or_none()
    if run is None or role not in {"research", "critic"}:
        raise RegistryError("unknown run or role")
    draft = c.execute(select(t.drafts).where(t.drafts.c.run_id == run_id)).mappings().one_or_none()
    if draft is None:
        raise RegistryError("NO_RECORDED_ACTION")
    critique = c.execute(select(t.critiques).where(t.critiques.c.draft_id == draft["id"])).mappings().one_or_none()
    if role == "critic" and critique is None:
        raise RegistryError("NO_RECORDED_ACTION")
    action_time = draft["created_at"] if role == "research" else critique["created_at"]
    definition = value(c, c.execute(select(t.agent_versions.c.definition_id).where(t.agent_versions.c.id == run[f"{role}_version"])).scalar_one())
    grounding_id = c.execute(select(t.run_events.c.detail_id).where(t.run_events.c.id == f"{run_id}:GROUNDING_CONTEXT")).scalar_one_or_none()
    manifest = value(c, c.execute(select(t.snapshots.c.manifest_id).where(t.snapshots.c.id == run["snapshot_id"])).scalar_one())
    tools = [{"name": row["name"], "allowed": bool(row["allowed"]), "arguments": value(c, row["arguments_id"]),
              "result_sha256": row["result_id"], "result": value(c, row["result_id"]), "at": row["created_at"].isoformat()}
             for row in c.execute(select(t.tool_calls).where(t.tool_calls.c.run_id == run_id, t.tool_calls.c.role == role,
                                                             t.tool_calls.c.created_at <= action_time)
                                  .order_by(t.tool_calls.c.created_at, t.tool_calls.c.id)).mappings()]
    proposal = parse_proposal(value(c, draft["artifact_id"]))
    parsed_critique = parse_critique(value(c, critique["artifact_id"])) if critique else None
    known = set(c.execute(select(t.drafts.c.signature).where(t.drafts.c.family_id == draft["family_id"],
                                                             t.drafts.c.created_at < draft["created_at"])).scalars())
    grounding = value(c, grounding_id) if grounding_id else None
    checks = review(proposal, parsed_critique if (role == "critic" and parsed_critique) else neutral_critique(proposal),
                    set(manifest["evidence"]), known, grounding).model_dump(mode="json")
    recorded_id = c.execute(select(t.run_events.c.detail_id).where(t.run_events.c.id == f"{run_id}:CONTRACT_REVIEW")).scalar_one_or_none()
    correction_id = c.execute(select(t.commitments.c.artifact_id).where(t.commitments.c.id == f"{draft['id']}:CONTRACT_REVIEW_CORRECTION")).scalar_one_or_none()
    invalidated = c.execute(select(t.run_events.c.id).where(t.run_events.c.id == f"{run_id}:PROCESS_CONTEXT_INVALIDATED")).scalar_one_or_none()
    corrections = [{**value(c, correction_id), "correction_sha256": correction_id}] if correction_id else []
    return {"version": PACKET_VERSION, "run_id": run_id, "role": role, "action_time": action_time.isoformat(),
            "information_cutoff": action_time.isoformat(), "task": value(c, run["task_id"]),
            "agent_definition": {key: definition.get(key) for key in ("role", "instruction_sha256", "tool_schema_sha256",
                                                                       "tool_policy", "research_contract_version", "workflow")},
            "grounding_context_sha256": grounding_id, "grounding_context": grounding, "tool_results": tools,
            "draft": {"sha256": draft["artifact_id"], **proposal.model_dump(mode="json")},
            "critique": ({"sha256": critique["artifact_id"], **parsed_critique.model_dump(mode="json")}
                         if critique and role == "critic" else None),
            "recorded_contract_review": ({"sha256": recorded_id, **value(c, recorded_id)} if recorded_id else None),
            "current_service_checks": {"policy": "deterministic contract checks recomputed under current code; not an outcome",
                                       "status": checks["status"], "reasons": checks["reasons"]},
            "test_basis": {"context_invalidated": bool(invalidated),
                           "review_corrections": [{key: item.get(key) for key in ("classification", "reason", "actor", "correction_sha256")}
                                                  for item in corrections],
                           "disputed_service_output": any(item.get("classification") in DISPUTED_SERVICE_OUTPUT for item in corrections)},
            "excluded": list(EXCLUDED_FROM_PACKET)}


def packet_hashes(packet):
    hashes = {packet["draft"]["sha256"], packet.get("grounding_context_sha256")}
    hashes.update(item["result_sha256"] for item in packet["tool_results"])
    if packet["critique"]:
        hashes.add(packet["critique"]["sha256"])
    if packet["recorded_contract_review"]:
        hashes.add(packet["recorded_contract_review"]["sha256"])
    return {item for item in hashes if item}


def resolve_reference(packet, reference):
    """A reference is a packet artifact hash or a dotted path that exists inside the packet."""
    if HEX64.match(reference):
        return "hash" if reference in packet_hashes(packet) else None
    root = re.split(r"[.\[]", reference, maxsplit=1)[0]
    if root not in PACKET_ROOTS:
        return None
    node = packet
    for part in re.findall(r"[^.\[\]]+|\[\d+\]", reference):
        try:
            node = node[int(part[1:-1])] if part.startswith("[") else node[part]
        except (KeyError, IndexError, TypeError):
            return None
    return root


def assessment_errors(command: ProcessAssessment, packet):
    reasons = []
    if digest(packet) != command.packet_sha256:
        reasons.append("PACKET_HASH_MISMATCH")
    if command.draft_sha256 != packet["draft"]["sha256"] or (command.critique_sha256 or None) != (
            packet["critique"]["sha256"] if packet["critique"] else None):
        reasons.append("ASSESSMENT_IDENTITY_MISMATCH")
    for finding in command.findings:
        roots = [resolve_reference(packet, reference) for reference in finding.references]
        if any(root is None for root in roots):
            reasons.append("REFERENCE_OUTSIDE_PACKET")
        agent_label = finding.status == "SUPPORTED" and finding.responsible_component in AGENT_COMPONENTS
        if agent_label and packet["test_basis"]["context_invalidated"]:
            reasons.append("INVALID_CONTEXT_YIELDS_NO_AGENT_LABEL")
        if agent_label and not any(root in ACTION_ROOTS or root == "hash" for root in roots):
            reasons.append("AGENT_FINDING_NEEDS_ACTION_REFERENCE")
        if agent_label and packet["test_basis"]["disputed_service_output"] and "recorded_contract_review" in roots:
            reasons.append("DISPUTED_LABEL_CANNOT_CONFIRM_AGENT_ERROR")
    return list(dict.fromkeys(reasons))


def assess_process(registry, command: ProcessAssessment):
    with registry.engine.begin() as c:
        packet = sealed_packet(c, command.run_id, command.role)
        errors = assessment_errors(command, packet)
        if errors:
            raise RegistryError(",".join(errors))
        agents = set(c.execute(select(t.agent_versions.c.id)).scalars())
        if command.assessor in agents or command.reviewer in agents:
            raise RegistryError("SELF_CERTIFICATION_REJECTED")
        if command.supersedes:
            prior = c.execute(select(t.assessments).where(t.assessments.c.id == command.supersedes)).mappings().one_or_none()
            if prior is None or prior["run_id"] != command.run_id or prior["role"] != command.role:
                raise RegistryError("SUPERSEDED_ASSESSMENT_MISMATCH")
            if c.execute(select(t.assessments.c.id).where(t.assessments.c.supersedes_id == prior["id"])).scalar_one_or_none():
                raise RegistryError("ALREADY_SUPERSEDED")
        for delta in command.critic_delta:
            linked = c.execute(select(t.assessments).where(t.assessments.c.id == delta.research_assessment_id)).mappings().one_or_none()
            if linked is None or linked["run_id"] != command.run_id or linked["role"] != "research":
                raise RegistryError("CRITIC_DELTA_LINK_INVALID")
        detail = {"version": ASSESSMENT_VERSION, **command.model_dump(mode="json"),
                  "information_cutoff": packet["information_cutoff"], "test_basis": packet["test_basis"]}
        identity = digest(detail)
        row = append(c, t.assessments, {"id": identity, "run_id": command.run_id, "role": command.role,
                                        "artifact_id": artifact(c, detail), "packet_id": artifact(c, packet),
                                        "supersedes_id": command.supersedes, "actor": command.assessor, "created_at": now()})
        return {"assessment_id": identity, "assessment_sha256": row["artifact_id"], "packet_sha256": row["packet_id"],
                "review_state": command.review_state, "findings": len(command.findings)}


def assessment_state(connection, assessment_id):
    """Derived, rebuildable integrity of one assessment; nothing here rewrites the record."""
    c = connection
    row = c.execute(select(t.assessments).where(t.assessments.c.id == assessment_id)).mappings().one_or_none()
    if row is None:
        return {"state": "UNKNOWN", "reasons": ["ASSESSMENT_MISSING"]}
    detail = value(c, row["artifact_id"])
    reasons = []
    if c.execute(select(t.assessments.c.id).where(t.assessments.c.supersedes_id == assessment_id)).scalar_one_or_none():
        reasons.append("SUPERSEDED")
    if detail["review_state"] != "REVIEWED":
        reasons.append("NOT_REVIEWED")
    if c.execute(select(t.run_events.c.id).where(t.run_events.c.id == f"{row['run_id']}:PROCESS_CONTEXT_INVALIDATED")).scalar_one_or_none():
        reasons.append("SOURCE_CONTEXT_INVALIDATED")
    draft = c.execute(select(t.drafts).where(t.drafts.c.run_id == row["run_id"])).mappings().one_or_none()
    if draft is not None:
        later = c.execute(select(t.commitments.c.id).where(t.commitments.c.draft_id == draft["id"],
            t.commitments.c.kind == "CONTRACT_REVIEW_CORRECTION", t.commitments.c.created_at > row["created_at"])).scalar_one_or_none()
        if later:
            reasons.append("SOURCE_LABEL_CORRECTED_PENDING_REVIEW")
    return {"state": "CURRENT" if not reasons else "SUSPENDED", "reasons": reasons, "review_state": detail["review_state"],
            "run_id": row["run_id"], "role": row["role"], "sha256": row["artifact_id"], "created_at": row["created_at"].isoformat()}
