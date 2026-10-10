"""The 2021 replication keeps the inspected parent's decision fixed."""

from hashlib import sha256
import json
from pathlib import Path

from tests.private_evidence import private_evidence_root


def _json(path: Path) -> dict:
    return json.loads(path.read_bytes())


def test_2021_replication_changes_only_identity_lineage_and_validation_window():
    repo = private_evidence_root()
    hypotheses = repo / "documents/research/hypotheses"
    parent_path = hypotheses / "eurusd_four_hour_direction_2020_v1.json"
    child_path = hypotheses / "eurusd_four_hour_direction_2021_replication_v1.json"
    parent = _json(parent_path)
    child = _json(child_path)
    selection_path = repo / "documents/research/evaluations/eurusd_four_hour_direction_2020_v1/selection"
    evidence_path = repo / "documents/research/evaluations/eurusd_four_hour_direction_2020_v1/evaluation"
    selection = _json(selection_path / "selection.json")

    for field in (
        "research_family", "loop", "evidence_mode", "economic_claim",
        "decision_contract", "feature_contract", "payoff_contract", "cost_contract",
        "development_window", "trial_budget", "search_space", "failure_reasons",
        "validation_release_rule",
    ):
        assert child[field] == parent[field]
    assert child["data_sufficiency_policy"] == parent["data_sufficiency_policy"]
    assert child["hypothesis_id"] == "eurusd_four_hour_direction_2021_replication_v1"
    assert child["parent_hypothesis_id"] == parent["hypothesis_id"]
    assert len(child["validation_windows"]) == 1
    assert child["validation_windows"][0] == {
        **parent["validation_windows"][0],
        "start_inclusive_utc": "2021-01-01T00:00:00Z",
        "end_exclusive_utc": "2022-01-01T00:00:00Z",
    }
    assert child["replication_of"] == {
        "parent_contract_sha256": sha256(parent_path.read_bytes()).hexdigest(),
        "parent_selection_sha256": sha256((selection_path / "selection.json").read_bytes()).hexdigest(),
        "parent_evidence_sha256": sha256((evidence_path / "evidence.json").read_bytes()).hexdigest(),
        "parent_baseline_class": selection["baseline_class"],
        "validation_window_basis": "next_complete_calendar_year_after_parent_validation",
        "parent_validation_was_inspected": True,
    }
    freeze = _json(hypotheses / "eurusd_four_hour_direction_2021_replication_v1.freeze.json")
    assert freeze["contract_sha256"] == sha256(child_path.read_bytes()).hexdigest()
    assert freeze["hypothesis_id"] == child["hypothesis_id"]
    coverage_path = repo / freeze["prevalidation_source_coverage_path"]
    coverage = _json(coverage_path)
    assert sha256(coverage_path.read_bytes()).hexdigest() == freeze["prevalidation_source_coverage_sha256"]
    assert coverage["contains_predictions_or_outcomes"] is False
    assert coverage["generated_at_utc"] < freeze["registered_at_utc"]
