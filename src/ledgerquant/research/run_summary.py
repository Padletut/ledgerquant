"""Readable, read-only view of an existing research run report."""

import json
from decimal import Decimal


def _value(item):
    return json.dumps(item, ensure_ascii=False, default=str)


def render_run_summary(report: dict) -> str:
    """Summarize recorded facts without changing their evidence status."""
    run = report["run"]
    events = report["events"]
    terminal = next((event for event in reversed(events)
                     if event["kind"] in {"FINISHED", "STOPPED"}), None)
    detail = terminal["detail"] if terminal else {}
    status = detail.get("status") or (terminal["kind"] if terminal else "UNKNOWN")
    calls = report["invocations"]
    reserved = sum(call["reserved_micro_usd"] for call in calls)
    outcomes = [call["outcome"] for call in calls if call["outcome"] is not None]
    complete_usage = [outcome for outcome in outcomes
                      if outcome["input_tokens"] is not None and outcome["output_tokens"] is not None]
    records = report["research_records"]
    lines = [f"Research run {run['id']}",
             f"Recorded status: {status}",
             f"Current integrity flag: {report['current_integrity']['status']}",
             f"Mode: {report['mode']}",
             f"Created: {_value(run['created_at'])}",
             f"Campaign: {run['campaign_id']}",
             f"Research version: {run['research_version']}",
             f"Critic version: {run['critic_version']}"]
    if detail.get("reason"):
        lines.append(f"Stop reason: {_value(detail['reason'])}")
    revision = next((event["detail"] for event in events if event["kind"] == "IDEA_REVISION"), None)
    if revision:
        lines.append(f"Parent idea draft: {revision['parent_draft_id']}")

    draft = records["draft"]
    lines.extend(["", "Idea or proposal"])
    if draft is None:
        lines.append("No recorded draft.")
    else:
        lines.append(f"Draft hash: {draft['sha256']}")
        body = draft["body"]
        for field in ("title", "question", "instruments", "candidate_information",
                      "proposed_decision", "proposed_payoff", "rationale", "falsifier",
                      "source_refs", "related_draft_ids", "measurement_gaps", "diagnostic",
                      "mechanism", "support", "contrary_evidence", "predicted_failure",
                      "admissibility_probability", "evidence_ids", "data_requirements"):
            if field in body:
                lines.append(f"{field}: {_value(body[field])}")
        if not any(field in body for field in ("title", "question")):
            lines.append("Full typed proposal is available in JSON replay.")

    critique = records["critique"]
    lines.extend(["", "Critic"])
    if critique is None:
        lines.append("No recorded critique.")
    else:
        lines.append(f"Critique hash: {critique['sha256']}")
        for field in ("summary", "disposition", "concerns", "objections"):
            if field in critique["body"]:
                lines.append(f"{field}: {_value(critique['body'][field])}")

    commitments = records["commitments"]
    if commitments:
        lines.extend(["", "Recorded commitments"])
        lines.extend(f"{item['kind']}: {item['sha256']}" for item in commitments)
    failures = [tool for tool in report["tools"]
                if not tool["allowed"] or (isinstance(tool["result"], dict) and tool["result"].get("error"))]
    lines.extend(["", "Resource record",
                  f"Invocations: {len(calls)}; outcomes recorded: {len(outcomes)}",
                  f"Reserved USD: {Decimal(reserved) / Decimal(1_000_000):.6f} (not billed cost)",
                  f"Reported tokens: input {sum(item['input_tokens'] for item in complete_usage)}, "
                  f"output {sum(item['output_tokens'] for item in complete_usage)} "
                  f"({len(complete_usage)}/{len(calls)} calls with complete usage)",
                  f"Rejected or errored tool calls: {len(failures)}",
                  "Exact inputs, events, tool results and outputs remain in JSON replay."])
    return "\n".join(lines) + "\n"
