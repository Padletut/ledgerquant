"""Frozen process schedule and reference scoring; no market-performance labels."""

from collections import defaultdict
from itertools import product
from statistics import mean

from .types import digest


def schedule(suite):
    """Interleave arms within task/repetition/time blocks; never select winners."""
    tasks = []
    for repetition, case in product(range(suite["repetitions"]), suite["cases"]):
        arms = suite["arms"] if repetition % 2 == 0 else list(reversed(suite["arms"]))
        for feedback, arm in product(suite["feedback_policies"], arms):
            tasks.append({"suite_sha256": digest(suite), "case_id": case["id"], "split": case["split"],
                          "repetition": repetition, "arm": arm, "feedback": feedback,
                          "proposal": case["proposal"], "economic_evaluation": False})
    return tasks


def score(suite, reports):
    by_task = {digest(report["task"]): report for report in reports}
    if len(by_task) != len(reports):
        raise ValueError("duplicate process-run report")
    groups, rows = defaultdict(list), []
    references = {case["id"]: case["reference"] for case in suite["cases"]}
    expected_tasks = schedule(suite)
    if set(by_task) - {digest(task) for task in expected_tasks}:
        raise ValueError("report does not belong to frozen suite")
    for task in expected_tasks:
        report = by_task.get(digest(task))
        invalid = bool(report and any(e["kind"] == "PROCESS_CONTEXT_INVALIDATED" for e in report["events"]))
        result = next((e["detail"] for e in report["events"] if e["kind"] == "PROCESS_RESULT"), None) if report else None
        reference = references[task["case_id"]]
        def correct(answer):
            return answer["disposition"] == reference["disposition"] and reference["required_reason"] in answer["reasons"]
        passed = bool(result and correct(result["answer"]))
        first = result.get("research_answer") if result else None
        row = {"case_id": task["case_id"], "split": task["split"], "arm": task["arm"],
               "feedback": task["feedback"], "repetition": task["repetition"],
               "run_id": report["run_id"] if report else None, "correct": passed,
               "evidence_integrity": "INVALID" if invalid else "UNCHANGED",
               "missing_or_failed": result is None,
               "critic_rescued": bool(task["arm"] == "critic" and first and not correct(first) and passed),
               "critic_introduced_error": bool(task["arm"] == "critic" and first and correct(first) and not passed),
               "reserved_micro_usd": report["reserved_micro_usd"] if report else 0,
               "confidence_brier": (result["answer"]["confidence"] - int(passed)) ** 2 if result else None}
        rows.append(row)
        groups[(task["feedback"], task["arm"], task["split"])].append(row)
    summary = []
    for (feedback, arm, split), group in groups.items():
        clusters = defaultdict(list)
        for row in group:
            clusters[row["case_id"]].append(int(row["correct"]))
        summary.append({"feedback": feedback, "arm": arm, "split": split, "runs": len(group),
            "task_templates": len(clusters), "task_mean_accuracy": None if any(row["evidence_integrity"] == "INVALID" for row in group) else mean(mean(values) for values in clusters.values()),
            "missing_or_failed": sum(row["missing_or_failed"] for row in group),
            "reserved_micro_usd": sum(row["reserved_micro_usd"] for row in group)})
    return {"suite_sha256": digest(suite), "scorer_version": "contract_process_reference/1",
            "integrity": "INVALID" if any(row["evidence_integrity"] == "INVALID" for row in rows) else "UNCHANGED",
            "reference_author": suite["reference_author"], "rows": rows, "summary": summary,
            "uncertainty": f"Descriptive only: {len(references)} correlated catalog templates; no generalization interval or discovery claim.",
            "economic_outcomes": "unmeasured; false economic rejection remains censored"}


def compact_report(task, report):
    return {"task": task, "run_id": report["run"]["id"], "events": report["events"],
            "reserved_micro_usd": sum(item["reserved_micro_usd"] for item in report["invocations"]),
            "input_tokens": sum(item["outcome"]["input_tokens"] or 0 for item in report["invocations"] if item["outcome"]),
            "output_tokens": sum(item["outcome"]["output_tokens"] or 0 for item in report["invocations"] if item["outcome"])}
