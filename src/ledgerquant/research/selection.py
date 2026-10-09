"""Freeze the one candidate and development-selected baseline before holdout measurement."""

from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path

from .contracts import ContractError
from .evaluation_data import load_evaluation_data
from .immutable import publish_directory
from .settlement import SettlementRequest, resolve_settlements, verify_source_sha256


def prediction_for_input(row: dict) -> str | None:
    if row["input_status"] != "ELIGIBLE":
        return None
    inputs = row["inputs"]
    if not inputs["anchor"]["eligible"] or not inputs["lookback"]["eligible"]:
        raise ContractError("input eligibility disagrees with quote references")
    anchor = Decimal(inputs["anchor"]["midquote"])
    lookback = Decimal(inputs["lookback"]["midquote"])
    return "PREDICT_UP" if anchor > lookback else "PREDICT_NON_UP"


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(rows: list[dict]) -> bytes:
    return b"".join(
        (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        for row in rows
    )


def _selection_code_sha256() -> str:
    digest = sha256()
    for name in ("selection.py", "evaluation_data.py", "settlement.py", "immutable.py"):
        module = Path(__file__).with_name(name)
        digest.update(name.encode("ascii") + b"\0" + module.read_bytes())
    return digest.hexdigest()


def prepare_selection(
    repo_root: Path,
    freeze_path: Path,
    audit_dir: Path,
    output_dir: Path,
) -> dict:
    """Use development outcomes only; freeze validation predictions from input quotes."""
    if output_dir.exists():
        raise ContractError(f"artifact output already exists: {output_dir}")
    data = load_evaluation_data(repo_root, freeze_path, audit_dir)
    verify_source_sha256(data.contract.source_file, data.contract.source_sha256)
    inputs = data.decision_inputs()
    if len(inputs) != data.audit_manifest["case_count"]:
        raise ContractError("decision input count differs from audit manifest")
    if len({row["case_id"] for row in inputs}) != len(inputs):
        raise ContractError("duplicate decision case ID")
    input_by_id = {row["case_id"]: row for row in inputs}
    development = data.development_eligibility()
    expected_dev_count = sum(data.audit_manifest["counts_by_window"]["development"].values())
    if len(development) != expected_dev_count:
        raise ContractError("development case count differs from audit manifest")
    if {row["case_id"] for row in development} != {
        row["case_id"] for row in inputs if row["window"] == "development"
    }:
        raise ContractError("development case identities differ from decision inputs")

    requests = [
        SettlementRequest(row["case_id"], row["settlement_target_utc"])
        for row in development if row["status"] == "MEASURABLE"
    ]
    settlements = resolve_settlements(
        data.contract.source_file,
        requests,
        data.contract.windows[0].end.isoformat().replace("+00:00", "Z"),
    )
    development_cases = []
    labels = Counter()
    for eligibility in development:
        case_id = eligibility["case_id"]
        decision = input_by_id[case_id]
        status = eligibility["status"]
        record = {
            "case_id": case_id,
            "anchor_utc": eligibility["anchor_utc"],
            "status": status,
            "candidate": prediction_for_input(decision),
            "target": None,
            "settlement_midquote": None,
            "settlement_source_line": None,
            "forward_midquote_change": None,
        }
        if status == "MEASURABLE":
            resolved = settlements[case_id]
            if resolved.event_at_utc != eligibility["settlement"]["event_at_utc"]:
                raise ContractError("development settlement disagrees with case audit")
            if record["candidate"] is None:
                raise ContractError("measurable case lacks a candidate prediction")
            anchor_midquote = Decimal(decision["inputs"]["anchor"]["midquote"])
            settlement_midquote = Decimal(resolved.midquote)
            change = settlement_midquote - anchor_midquote
            target = "PREDICT_UP" if change > 0 else "PREDICT_NON_UP"
            record.update(
                target=target,
                settlement_midquote=resolved.midquote,
                settlement_source_line=resolved.source_line,
                forward_midquote_change=format(change, "f"),
            )
            labels[target] += 1
        development_cases.append(record)

    baseline_class = (
        "PREDICT_UP" if labels["PREDICT_UP"] > labels["PREDICT_NON_UP"]
        else "PREDICT_NON_UP"
    )
    measurable = sum(row["status"] == "MEASURABLE" for row in development_cases)
    for record in development_cases:
        record["baseline"] = baseline_class if record["target"] is not None else None
        record["candidate_correct"] = (
            record["candidate"] == record["target"] if record["target"] is not None else None
        )
        record["baseline_correct"] = (
            baseline_class == record["target"] if record["target"] is not None else None
        )
    dev_gate = data.audit_manifest["data_sufficiency_gates"]["development"]
    gate_passed = bool(dev_gate["minimum_eligible_anchors_met"] and dev_gate["maximum_unmeasurable_fraction_met"])
    selection_status = "CANDIDATE_FROZEN" if gate_passed else "DEVELOPMENT_DATA_FAILED"
    predictions = []
    if gate_passed:
        for row in inputs:
            if row["window"] != "validation":
                continue
            candidate = prediction_for_input(row)
            predictions.append(
                {
                    "case_id": row["case_id"],
                    "anchor_utc": row["anchor_utc"],
                    "candidate": candidate,
                    "baseline": baseline_class if candidate is not None else None,
                }
            )
    dev_bytes = _jsonl_bytes(development_cases)
    prediction_bytes = _jsonl_bytes(predictions)
    selected_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    selection = {
        "schema_version": 1,
        "hypothesis_id": data.contract.hypothesis_id,
        "trial_id": f"{data.contract.hypothesis_id}:trial_1",
        "selection_status": selection_status,
        "contract_sha256": data.contract.contract_sha256,
        "audit_manifest_sha256": data.audit_manifest_sha256,
        "source_sha256": data.contract.source_sha256,
        "selection_code_sha256": _selection_code_sha256(),
        "candidate_rule": "prior_hour_midquote_momentum_sign",
        "baseline_rule": "majority_development_target_class",
        "baseline_class": baseline_class,
        "development_cases_file": "development_cases.jsonl",
        "development_cases_sha256": sha256(dev_bytes).hexdigest(),
        "validation_predictions_file": "validation_predictions.jsonl",
        "validation_predictions_sha256": sha256(prediction_bytes).hexdigest(),
        "development_summary": {
            "scheduled_count": len(development_cases),
            "measurable_count": measurable,
            "target_counts": dict(labels),
            "candidate_accuracy": (
                sum(row["candidate_correct"] for row in development_cases if row["target"] is not None) / measurable
                if measurable else None
            ),
            "baseline_accuracy": (
                sum(row["baseline_correct"] for row in development_cases if row["target"] is not None) / measurable
                if measurable else None
            ),
            "data_sufficiency_gates": dev_gate,
        },
        "validation_prediction_count": len(predictions),
        "selected_at_utc": selected_at,
        "contains_validation_outcomes": False,
    }
    selection_bytes = _json_bytes(selection)
    selection_freeze = {
        "schema_version": 1,
        "event_type": (
            "CANDIDATE_SELECTION_FROZEN" if gate_passed
            else "DEVELOPMENT_ATTEMPT_RECORDED"
        ),
        "hypothesis_id": data.contract.hypothesis_id,
        "selection_sha256": sha256(selection_bytes).hexdigest(),
        "frozen_at_utc": selected_at,
    }
    publish_directory(
        output_dir,
        {
            "development_cases.jsonl": dev_bytes,
            "validation_predictions.jsonl": prediction_bytes,
            "selection.json": selection_bytes,
            "selection.freeze.json": _json_bytes(selection_freeze),
        },
    )
    return selection
