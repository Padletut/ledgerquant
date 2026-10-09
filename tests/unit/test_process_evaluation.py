import json
from pathlib import Path

from ledgerquant.agents.process_runtime import checklist
from ledgerquant.research.imports import LEGACY_IDS
from ledgerquant.research.process_evaluation import schedule, score


def suite():
    return json.loads((Path(__file__).parents[2] / "configs/research/contract_process_suite.json").read_text())


def test_schedule_keeps_reference_labels_out_of_agent_tasks():
    tasks = schedule(suite())
    assert len(tasks) == 36
    assert all("reference" not in task for task in tasks)
    assert {task["arm"] for task in tasks} == {"single", "critic", "checklist"}
    assert {task["feedback"] for task in tasks} == {"none", "structured"}


def test_checklist_against_frozen_reference_cases():
    for case in suite()["cases"]:
        answer = checklist(case["proposal"], LEGACY_IDS)
        assert answer.disposition == case["reference"]["disposition"]
        assert case["reference"]["required_reason"] in answer.reasons


def test_missing_runs_count_as_failures_without_economic_claim():
    result = score(suite(), [])
    assert len(result["rows"]) == 36
    assert all(row["missing_or_failed"] for row in result["rows"])
    assert all(row["task_mean_accuracy"] == 0 for row in result["summary"])
    assert "censored" in result["economic_outcomes"]
