"""Read-only, human-readable views of recorded assessments and their exact packets."""

from html import escape
import json
import re

from sqlalchemy import select

from . import tables as t
from .process_assessment import assessment_state, resolve_reference, sealed_packet
from .registry import RegistryError, now, value
from .types import digest


DEFECT_LABELS = {
    "REQUIREMENT_SCOPE_CONFUSION": "Current versus future data requirements",
    "EVIDENCE_MISATTRIBUTION": "Evidence attributed to the wrong scope",
    "DUPLICATE_LINEAGE_ERROR": "Same idea, duplicate or linked revision",
    "NON_PREDICTIVE_FALSIFIER": "Predictive falsification versus admission rules",
    "OMITTED_CONTRARY_EVIDENCE": "Missing contrary evidence",
    "UNSUPPORTED_CAUSAL_CLAIM": "Unsupported causal explanation",
    "STATUS_MISINTERPRETATION": "Incorrect interpretation of a research status",
}
STATUS_LABELS = {
    "SUPPORTED": "the alleged defect is supported",
    "NOT_SUPPORTED": "the alleged defect is not supported",
    "UNRESOLVED": "the available evidence does not settle the allegation",
}


def review_process(connection, assessment_id):
    """Export stored sources and current integrity; never register a review decision."""
    row = connection.execute(select(t.assessments).where(t.assessments.c.id == assessment_id)).mappings().one_or_none()
    if row is None:
        raise RegistryError("ASSESSMENT_MISSING")
    detail, packet = value(connection, row["artifact_id"]), value(connection, row["packet_id"])
    if digest(detail) != row["artifact_id"] or row["id"] != row["artifact_id"]:
        raise RegistryError("REVIEW_SOURCE_HASH_MISMATCH")
    return {"version": "process_review/1", "assessment_id": assessment_id, "assessment": detail,
            "packet_sha256": row["packet_id"], "packet": packet, "recorded_at": row["created_at"].isoformat(),
            "source_state": assessment_state(connection, assessment_id), "exported_at": now().isoformat(),
            "current_packet_sha256": digest(sealed_packet(connection, row["run_id"], row["role"]))}


def _block(content):
    if isinstance(content, str):
        # Quotations wrap as prose while model-authored Markdown stays literal.
        body = re.sub(r"([\\`*_\[\]#])", r"\\\1", escape(content, quote=False))
        return "\n".join("> " + line for line in body.splitlines()) or "> (empty string)"
    body = json.dumps(content, indent=2, ensure_ascii=False)
    fence = "`" * max(3, 1 + max((len(m) for m in re.findall(r"`+", body)), default=0))
    return f"{fence}json\n{body}\n{fence}"


def _reference_values(packet):
    """Index the exact packet paths; the assessment contract validates allowed roots."""
    result = {}

    def visit(node, path):
        result[path] = node
        if isinstance(node, dict):
            for key, child in node.items():
                visit(child, f"{path}.{key}" if path else key)
        elif isinstance(node, list):
            for index, child in enumerate(node):
                visit(child, f"{path}[{index}]")

    visit(packet, "")
    for key in ("draft", "critique", "recorded_contract_review"):
        if packet.get(key):
            result[packet[key]["sha256"]] = packet[key]
    if packet.get("grounding_context_sha256"):
        result[packet["grounding_context_sha256"]] = packet["grounding_context"]
    for item in packet["tool_results"]:
        result[item["result_sha256"]] = item["result"]
    return result


def render_process_review(bundle, *, source_link=None):
    """Preserve the recorded review state, full cited values and absence of outcome scores."""
    assessment, packet = bundle["assessment"], bundle["packet"]
    if (bundle["version"] != "process_review/1" or digest(assessment) != bundle["assessment_id"]
            or digest(packet) != bundle["packet_sha256"]
            or assessment["packet_sha256"] != bundle["packet_sha256"]):
        raise RegistryError("REVIEW_SOURCE_HASH_MISMATCH")
    if (assessment["run_id"], assessment["role"]) != (packet["run_id"], packet["role"]):
        raise RegistryError("ASSESSMENT_IDENTITY_MISMATCH")
    references = _reference_values(packet)
    reviewed = assessment["review_state"] == "REVIEWED"
    label = "Reviewed finding" if reviewed else "Assessor's proposed label"
    lines = [f"# Process review: {assessment['role'].title()} — {assessment['run_id'][:8]}",
             ("This is a derived reading view of a completed review. The findings preserve its "
              "recorded decisions; exporting or reading this document does not change them." if reviewed else
              "This is a derived reading view. All findings below are the recorded assessor's claims; "
              "exporting or reading this document does not approve them."),
             "## Recorded review" if reviewed else "## What you are reviewing", _block(assessment["reason"]),
             f"- Recorded review state: **{assessment['review_state']}**.\n"
             f"- Assessor outcome exposure: **{assessment['assessor_outcome_exposure']}**.\n"
             f"- Recorded at: `{bundle['recorded_at']}`.\n"
             f"- Exported at: `{bundle.get('exported_at', 'not recorded')}`.\n"
             f"- Agent action time: `{packet['action_time']}`.",
             "You are assessing whether each process allegation follows from the cited information and "
             "the rules then in force, including attribution, severity and applicability. "
             "A process review does not certify predictive value, trading profitability or general agent quality."]
    if source_link:
        lines.append(f"[Complete source packet and assessment]({source_link})")
    if bundle["current_packet_sha256"] != bundle["packet_sha256"]:
        lines.extend(["**SOURCE CHANGED.** Obtain a current packet before submitting a replacement assessment. "
                      "This document preserves the packet used by the original assessor."])
    lines.extend(["**Review availability:** " + ("awaiting human review." if bundle["source_state"]["reasons"] == ["NOT_REVIEWED"]
                  else ", ".join(bundle["source_state"]["reasons"]) or bundle["source_state"]["state"]),
                  "## Decision key",
                  "- `SUPPORTED`: the alleged defect is supported by the evidence.\n"
                  "- `NOT_SUPPORTED`: the allegation is not supported; this is not a blanket quality certificate.\n"
                  "- `UNRESOLVED`: keep the question open and record what is missing.\n"
                  "- `REVIEWED`: a reviewer has assessed the record; it does not mean every allegation was accepted.",
                  "## Findings"])
    for index, finding in enumerate(assessment["findings"], 1):
        lines.extend([f"### F{index} — {DEFECT_LABELS[finding['code']]}",
                      f"**{label}:** `{finding['status']}` — {STATUS_LABELS[finding['status']]}.\n\n"
                      f"**Component:** `{finding['responsible_component']}`. **Severity:** `{finding['severity']}`.",
                      "**Recorded explanation:**" if reviewed else "**Claim to check:**", _block(finding["explanation"]),
                      "**Applicability claimed:**", _block(finding["applicability"]),
                      "**Exact cited source values:**"])
        for reference in finding["references"]:
            if resolve_reference(packet, reference) is None or reference not in references:
                raise RegistryError("REFERENCE_OUTSIDE_PACKET")
            lines.extend([f"Source: `{reference}`", _block(references[reference])])
        if not reviewed:
            lines.append("**Your decision:** retain or change the label, component, severity or explanation. "
                         "If the sources do not establish the claim, use `NOT_SUPPORTED` or `UNRESOLVED` "
                         "and explain the limitation. No decision has been selected for you.")
    if assessment["critic_delta"]:
        lines.extend(["## Critic comparisons",
                      "Check these comparisons after reviewing the Research assessment. `MISSED` alleges "
                      "a missed Research defect; `INTRODUCED` alleges a new defect; `RESCUED` alleges "
                      "a correction; `CONFIRMED` alleges a consistent assessment. Check the cited finding, "
                      "not just agreement between agents. A replacement Critic record should link to the "
                      "Research assessment version you actually reviewed.", _block(assessment["critic_delta"])])
    lines.extend(["## Assessor limitations", *[_block(item) for item in assessment["limitations"]],
                  "## Original task", _block(packet["task"]),
                  "## Original draft", _block(packet["draft"])])
    if packet["critique"]:
        lines.extend(["## Original Critic response", _block(packet["critique"])])
    lines.append("## Catalog and requirement rules actually supplied")
    for index, item in enumerate(packet["tool_results"]):
        if item["name"] == "read_source_coverage" and item["allowed"]:
            for key in ("catalog", "requirement_rules"):
                if key in item["result"]:
                    lines.extend([f"Source: `tool_results[{index}].result.{key}`", _block(item["result"][key])])
    lines.extend(["## Rules and test-basis context",
                  "The complete source export contains the task, tool results and frozen context. "
                  "The following test-basis annotations and service checks are retrospective context, "
                  "not statements authored by the agent.", _block(packet["agent_definition"]),
                  _block(packet["test_basis"]), _block(packet["current_service_checks"]),
                  "## Recording a further review" if reviewed else "## Recording your review",
                  "Keep the original record. Submit a new `assess-process` command only after making "
                  "your decisions: `supersedes` names the assessment below, `reviewer` identifies the "
                  "human reviewer, and the new assessor declares their actual outcome exposure. "
                  "Retain unresolved findings where appropriate. Original authorship and declarations "
                  "remain in the superseded record.",
                  "Before submission, regenerate this view to check for changed or superseded sources. "
                  "Only your explicit review decision permits recording a reviewed replacement.",
                  "## Audit metadata",
                  f"Assessment to supersede: `{bundle['assessment_id']}`.\n\n"
                  f"Packet hash: `{bundle['packet_sha256']}`.",
                  "Original assessor:", _block(assessment["assessor"]),
                  "Registry integrity at export:", _block(bundle["source_state"])])
    if reviewed:
        lines.extend(["Recorded reviewer:", _block(assessment["reviewer"]),
                      "Superseded assessment:", _block(assessment.get("supersedes"))])
    return "\n\n".join(lines) + "\n"
