import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from ledgerquant.research.artifacts import publish_audit
from ledgerquant.research.audit import audit_cases
from ledgerquant.research.contracts import ContractError, load_frozen_contract
from ledgerquant.research.evaluator import evaluate_selection
from ledgerquant.research.metrics import bootstrap_lower_bound
from ledgerquant.research.selection import prepare_selection
from ledgerquant.research.settlement import SettlementRequest, resolve_settlements


BASE_CONTRACT = json.loads(
    (
        Path(__file__).parents[2]
        / "documents/research/hypotheses/eurusd_four_hour_direction_2020_v1.json"
    ).read_text(encoding="utf-8")
)


def research_fixture(tmp_path: Path):
    source = tmp_path / "ticks.csv"
    source.write_text(
        "\n".join(
            [
                "2020-01-02,07:00:00.000,1.00000,1.00010",
                "2020-01-02,08:00:00.000,1.00100,1.00110",
                "2020-01-02,12:00:00.000,1.00200,1.00210",
                "2020-01-03,07:00:00.000,1.00000,1.00010",
                "2020-01-03,08:00:00.000,1.00100,1.00110",
                "2020-01-03,12:00:00.000,1.00050,1.00060",
            ]
        )
        + "\n",
        encoding="ascii",
    )
    contract = deepcopy(BASE_CONTRACT)
    contract["feature_contract"]["source_file"] = "ticks.csv"
    contract["feature_contract"]["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    contract["decision_contract"]["candidate_event_rule"]["hours_utc"] = [8]
    contract["development_window"].update(
        start_inclusive_utc="2020-01-02T00:00:00Z",
        end_exclusive_utc="2020-01-03T00:00:00Z",
        minimum_eligible_anchors=1,
    )
    contract["validation_windows"][0].update(
        start_inclusive_utc="2020-01-03T00:00:00Z",
        end_exclusive_utc="2020-01-04T00:00:00Z",
        minimum_eligible_anchors=1,
    )
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "event_type": "CONTRACT_FROZEN",
                "hypothesis_id": contract["hypothesis_id"],
                "contract_path": "contract.json",
                "contract_sha256": hashlib.sha256(contract_path.read_bytes()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    audit_dir = tmp_path / "audit"
    publish_audit(audit_cases(load_frozen_contract(tmp_path, freeze_path), tmp_path), audit_dir)
    return source, freeze_path, audit_dir


def test_selection_freezes_predictions_before_independent_validation(tmp_path):
    _, freeze_path, audit_dir = research_fixture(tmp_path)
    selection_dir = tmp_path / "selection"
    selection = prepare_selection(tmp_path, freeze_path, audit_dir, selection_dir)

    assert selection["baseline_class"] == "PREDICT_UP"
    assert selection["development_summary"]["measurable_count"] == 1
    assert selection["development_summary"]["candidate_accuracy"] == 1.0
    predictions = [
        json.loads(line)
        for line in (selection_dir / "validation_predictions.jsonl").read_text().splitlines()
    ]
    assert predictions[0]["candidate"] == "PREDICT_UP"
    assert predictions[0]["baseline"] == "PREDICT_UP"
    assert "target" not in predictions[0]
    assert "settlement" not in predictions[0]

    evidence_dir = tmp_path / "evidence"
    evidence = evaluate_selection(tmp_path, freeze_path, audit_dir, selection_dir, evidence_dir)
    assert evidence["validation"]["measurable_count"] == 1
    assert evidence["validation"]["paired_accuracy_difference"] == 0.0
    assert evidence["validation"]["bootstrap_lower_bound"] == 0.0
    assert evidence["gate_decision"] == "TEMPORAL_FAILED"
    assert evidence["failure_reason"] == "TEMPORAL_FAILURE"
    assert evidence["economic_claim"] == "none_predictive_diagnostic_only"
    with pytest.raises(ContractError, match="already exists"):
        evaluate_selection(tmp_path, freeze_path, audit_dir, selection_dir, evidence_dir)


def test_evaluator_rejects_predictions_changed_after_freeze(tmp_path):
    _, freeze_path, audit_dir = research_fixture(tmp_path)
    selection_dir = tmp_path / "selection"
    prepare_selection(tmp_path, freeze_path, audit_dir, selection_dir)
    predictions = selection_dir / "validation_predictions.jsonl"
    predictions.write_text(predictions.read_text() + "\n")

    with pytest.raises(ContractError, match="prediction SHA-256"):
        evaluate_selection(tmp_path, freeze_path, audit_dir, selection_dir, tmp_path / "evidence")
    assert not (tmp_path / "evidence").exists()


def test_development_settlement_reader_stops_before_validation_rows(tmp_path):
    source = tmp_path / "ticks.csv"
    source.write_text(
        "2020-01-02,12:00:00.000,1.00200,1.00210\n"
        "2020-01-03,08:00:00.000,invalid,invalid\n",
        encoding="ascii",
    )
    result = resolve_settlements(
        source,
        [SettlementRequest("dev", "2020-01-02T12:00:00Z")],
        "2020-01-03T00:00:00Z",
    )
    assert result["dev"].midquote == "1.00205"


def test_daily_block_bootstrap_keeps_all_cases_from_sampled_day():
    rows = [
        {"anchor_utc": "2020-07-01T08:00:00Z", "candidate_correct": True, "baseline_correct": False},
        {"anchor_utc": "2020-07-01T12:00:00Z", "candidate_correct": True, "baseline_correct": False},
        {"anchor_utc": "2020-07-02T08:00:00Z", "candidate_correct": False, "baseline_correct": True},
    ]
    first = bootstrap_lower_bound(rows, 1000, 42, 5)
    assert first == bootstrap_lower_bound(rows, 1000, 42, 5)
    assert first == -1.0
