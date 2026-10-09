"""Independent offline validation of the frozen EURUSD diagnostic trial."""

from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path

from .contracts import ContractError
from .evaluation_data import load_evaluation_data
from .immutable import publish_directory
from .metrics import summarize_validation
from .selection import _selection_code_sha256, prediction_for_input
from .settlement import SettlementRequest, resolve_settlements, verify_source_sha256


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(rows: list[dict]) -> bytes:
    return b"".join(
        (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        for row in rows
    )


def _load_selection(selection_dir: Path, data) -> tuple[dict, list[dict], str]:
    try:
        selection_bytes = (selection_dir / "selection.json").read_bytes()
        frozen = json.loads((selection_dir / "selection.freeze.json").read_bytes())
        selection = json.loads(selection_bytes)
        if frozen["schema_version"] != 1 or frozen["event_type"] != "CANDIDATE_SELECTION_FROZEN":
            raise ContractError("candidate selection is not frozen")
        if frozen["hypothesis_id"] != data.contract.hypothesis_id:
            raise ContractError("selection freeze identity mismatch")
        if frozen["frozen_at_utc"] != selection["selected_at_utc"]:
            raise ContractError("selection freeze time mismatch")
        for field in ("validation_predictions_file", "development_cases_file"):
            if Path(selection[field]).name != selection[field]:
                raise ContractError("selection artifact path escapes its directory")
        predictions_bytes = (selection_dir / selection["validation_predictions_file"]).read_bytes()
        development_bytes = (selection_dir / selection["development_cases_file"]).read_bytes()
        if sha256(selection_bytes).hexdigest() != frozen["selection_sha256"]:
            raise ContractError("selection SHA-256 mismatch")
        if sha256(predictions_bytes).hexdigest() != selection["validation_predictions_sha256"]:
            raise ContractError("prediction SHA-256 mismatch")
        if sha256(development_bytes).hexdigest() != selection["development_cases_sha256"]:
            raise ContractError("development evidence SHA-256 mismatch")
        if selection["selection_status"] != "CANDIDATE_FROZEN":
            raise ContractError("candidate selection did not pass development data gate")
        if selection["contract_sha256"] != data.contract.contract_sha256:
            raise ContractError("selection contract SHA-256 mismatch")
        if selection["audit_manifest_sha256"] != data.audit_manifest_sha256:
            raise ContractError("selection audit manifest SHA-256 mismatch")
        if selection["source_sha256"] != data.contract.source_sha256:
            raise ContractError("selection source SHA-256 mismatch")
        if selection["selection_code_sha256"] != _selection_code_sha256():
            raise ContractError("selection code SHA-256 mismatch")
        predictions = [json.loads(line) for line in predictions_bytes.splitlines()]
        development_cases = [json.loads(line) for line in development_bytes.splitlines()]
        labels = Counter(row["target"] for row in development_cases if row["target"] is not None)
        expected_baseline = (
            "PREDICT_UP" if labels["PREDICT_UP"] > labels["PREDICT_NON_UP"]
            else "PREDICT_NON_UP"
        )
        if selection["baseline_class"] != expected_baseline:
            raise ContractError("frozen baseline disagrees with development targets")
        if len(development_cases) != selection["development_summary"]["scheduled_count"]:
            raise ContractError("development evidence count mismatch")
        if sum(row["target"] is not None for row in development_cases) != selection["development_summary"]["measurable_count"]:
            raise ContractError("development measured count mismatch")
        if any(set(row) != {"case_id", "anchor_utc", "candidate", "baseline"} for row in predictions):
            raise ContractError("prediction artifact contains unexpected fields")
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ContractError(f"invalid frozen selection: {exc}") from exc
    return selection, predictions, sha256(selection_bytes).hexdigest()


def _evaluation_code_sha256() -> str:
    digest = sha256()
    for name in (
        "evaluator.py", "metrics.py", "settlement.py", "evaluation_data.py",
        "selection.py", "immutable.py",
    ):
        module = Path(__file__).with_name(name)
        digest.update(name.encode("ascii") + b"\0" + module.read_bytes())
    return digest.hexdigest()


def evaluate_selection(
    repo_root: Path,
    freeze_path: Path,
    audit_dir: Path,
    selection_dir: Path,
    output_dir: Path,
) -> dict:
    """Open validation outcomes only after a complete frozen selection is verified."""
    if output_dir.exists():
        raise ContractError(f"artifact output already exists: {output_dir}")
    if not selection_dir.resolve().is_relative_to(repo_root.resolve()):
        raise ContractError("selection directory escapes repository root")
    data = load_evaluation_data(repo_root, freeze_path, audit_dir)
    selection, predictions, selection_sha = _load_selection(selection_dir, data)
    inputs = [row for row in data.decision_inputs() if row["window"] == "validation"]
    eligibility = data.validation_eligibility()
    if not (len(inputs) == len(eligibility) == len(predictions)):
        raise ContractError("validation case counts disagree")
    input_by_id = {row["case_id"]: row for row in inputs}
    prediction_by_id = {row["case_id"]: row for row in predictions}
    if len(input_by_id) != len(inputs) or len(prediction_by_id) != len(predictions):
        raise ContractError("duplicate validation case ID")
    if set(input_by_id) != set(prediction_by_id) or set(input_by_id) != {row["case_id"] for row in eligibility}:
        raise ContractError("validation case identities disagree")
    for case_id, prediction in prediction_by_id.items():
        expected = prediction_for_input(input_by_id[case_id])
        if prediction["candidate"] != expected:
            raise ContractError("frozen candidate prediction disagrees with input")
        expected_baseline = selection["baseline_class"] if expected is not None else None
        if prediction["baseline"] != expected_baseline:
            raise ContractError("frozen baseline prediction disagrees with selection")

    verify_source_sha256(data.contract.source_file, data.contract.source_sha256)
    requests = [
        SettlementRequest(row["case_id"], row["settlement_target_utc"])
        for row in eligibility if row["status"] == "MEASURABLE"
    ]
    settlements = resolve_settlements(
        data.contract.source_file,
        requests,
        data.contract.windows[1].end.isoformat().replace("+00:00", "Z"),
    )
    cases = []
    for row in eligibility:
        case_id = row["case_id"]
        prediction = prediction_by_id[case_id]
        record = {
            "case_id": case_id,
            "anchor_utc": row["anchor_utc"],
            "status": row["status"],
            "candidate": prediction["candidate"],
            "baseline": prediction["baseline"],
            "target": None,
            "settlement_midquote": None,
            "settlement_source_line": None,
            "forward_midquote_change": None,
            "candidate_correct": None,
            "baseline_correct": None,
        }
        if row["status"] == "MEASURABLE":
            resolved = settlements[case_id]
            if resolved.event_at_utc != row["settlement"]["event_at_utc"]:
                raise ContractError("validation settlement disagrees with case audit")
            if prediction["candidate"] is None or prediction["baseline"] is None:
                raise ContractError("measurable case lacks frozen predictions")
            anchor_midquote = Decimal(input_by_id[case_id]["inputs"]["anchor"]["midquote"])
            settlement_midquote = Decimal(resolved.midquote)
            change = settlement_midquote - anchor_midquote
            target = "PREDICT_UP" if change > 0 else "PREDICT_NON_UP"
            record.update(
                target=target,
                settlement_midquote=resolved.midquote,
                settlement_source_line=resolved.source_line,
                forward_midquote_change=format(change, "f"),
                candidate_correct=prediction["candidate"] == target,
                baseline_correct=prediction["baseline"] == target,
            )
        cases.append(record)

    validation_summary, gate_decision, failure_reason = summarize_validation(
        cases,
        data.contract.windows[1],
        data.contract.maximum_unmeasurable_fraction,
        data.spec["payoff_contract"]["uncertainty"],
    )
    cases_bytes = _jsonl_bytes(cases)
    evidence = {
        "schema_version": 1,
        "hypothesis_id": data.contract.hypothesis_id,
        "trial_id": selection["trial_id"],
        "evidence_mode": "retrospective_historical_simulation",
        "economic_claim": "none_predictive_diagnostic_only",
        "promotion_eligible": False,
        "contract_sha256": data.contract.contract_sha256,
        "audit_manifest_sha256": data.audit_manifest_sha256,
        "selection_sha256": selection_sha,
        "source_sha256": data.contract.source_sha256,
        "evaluation_code_sha256": _evaluation_code_sha256(),
        "validation_cases_file": "validation_cases.jsonl",
        "validation_cases_sha256": sha256(cases_bytes).hexdigest(),
        "related_trial_count": 1,
        "validation": validation_summary,
        "gate_decision": gate_decision,
        "failure_reason": failure_reason,
        "cost_stress": "not_applicable_no_trade",
        "drawdown_and_tail_risk": "not_applicable_no_trade",
        "calibration": "not_applicable_no_probability_output",
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    evidence_bytes = _json_bytes(evidence)
    freeze = {
        "schema_version": 1,
        "event_type": "EVALUATION_RECORDED",
        "hypothesis_id": data.contract.hypothesis_id,
        "evidence_sha256": sha256(evidence_bytes).hexdigest(),
    }
    publish_directory(
        output_dir,
        {
            "validation_cases.jsonl": cases_bytes,
            "evidence.json": evidence_bytes,
            "evidence.freeze.json": _json_bytes(freeze),
        },
    )
    return evidence
