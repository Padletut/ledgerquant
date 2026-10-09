"""Publish separate decision input and evaluator eligibility artifacts."""

from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile

from .audit import CaseAudit
from .contracts import ContractError


AUDIT_VERSION = 1


def _jsonl(rows: list[dict]) -> bytes:
    return b"".join(
        (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        for row in rows
    )


def _code_sha256() -> str:
    digest = sha256()
    for name in ("contracts.py", "audit.py", "artifacts.py"):
        module = Path(__file__).with_name(name)
        digest.update(name.encode("ascii") + b"\0" + module.read_bytes())
    return digest.hexdigest()


def publish_audit(audit: CaseAudit, output_dir: Path) -> dict:
    """Publish the verified view once; never replace an existing audit directory."""
    if output_dir.exists():
        raise ContractError(f"audit output already exists: {output_dir}")

    decision_inputs = []
    case_eligibility = []
    counts_by_month = defaultdict(Counter)
    for case in audit.cases:
        input_status = (
            "ELIGIBLE" if all(item["eligible"] for item in case["inputs"].values())
            else "INPUT_MISSING"
        )
        decision_inputs.append(
            {
                "case_id": case["case_id"],
                "window": case["window"],
                "anchor_utc": case["anchor_utc"],
                "assumed_decision_at_utc": case["assumed_decision_at_utc"],
                "input_status": input_status,
                "inputs": case["inputs"],
            }
        )
        case_eligibility.append(
            {
                "case_id": case["case_id"],
                "window": case["window"],
                "anchor_utc": case["anchor_utc"],
                "input_status": input_status,
                "settlement_target_utc": case["settlement_target_utc"],
                "settlement": case["settlement"],
                "status": case["status"],
            }
        )
        counts_by_month[case["anchor_utc"][:7]][case["status"]] += 1

    counts_by_window = {}
    gates = {}
    statuses = ("MEASURABLE", "INPUT_MISSING", "OUTCOME_MISSING")
    for window in audit.contract.windows:
        window_cases = [case for case in audit.cases if case["window"] == window.name]
        counts = Counter(case["status"] for case in window_cases)
        counts_by_window[window.name] = {status: counts[status] for status in statuses}
        unmeasurable = len(window_cases) - counts["MEASURABLE"]
        gates[window.name] = {
            "minimum_eligible_anchors_met": (
                counts["MEASURABLE"] >= window.minimum_eligible_anchors
            ),
            "maximum_unmeasurable_fraction_met": (
                bool(window_cases)
                and unmeasurable / len(window_cases)
                <= audit.contract.maximum_unmeasurable_fraction
            ),
        }

    inputs_bytes = _jsonl(decision_inputs)
    eligibility_bytes = _jsonl(case_eligibility)
    manifest = {
        "schema_version": 1,
        "audit_version": AUDIT_VERSION,
        "hypothesis_id": audit.contract.hypothesis_id,
        "evidence_mode": "retrospective_historical_simulation",
        "contract_sha256": audit.contract.contract_sha256,
        "freeze_sha256": audit.contract.freeze_sha256,
        "audit_code_sha256": _code_sha256(),
        "source_id": audit.contract.source_id,
        "instrument": audit.contract.instrument,
        "source_sha256": audit.contract.source_sha256,
        "source_bytes": audit.source_bytes,
        "source_rows_in_scope": audit.source_rows_in_scope,
        "source_scan_start_inclusive_utc": (
            audit.contract.windows[0].start.isoformat().replace("+00:00", "Z")
        ),
        "source_scan_end_exclusive_utc": (
            audit.contract.windows[-1].end.isoformat().replace("+00:00", "Z")
        ),
        "decision_inputs_file": "decision_inputs.jsonl",
        "decision_inputs_sha256": sha256(inputs_bytes).hexdigest(),
        "case_eligibility_file": "case_eligibility.jsonl",
        "case_eligibility_sha256": sha256(eligibility_bytes).hexdigest(),
        "case_count": len(audit.cases),
        "counts_by_window": counts_by_window,
        "counts_by_month": {
            month: {status: counts[status] for status in statuses}
            for month, counts in sorted(counts_by_month.items())
        },
        "data_sufficiency_gates": gates,
        "contains_predictions_or_outcome_prices": False,
        "generated_at_utc": (
            datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        ),
    }

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent)
    )
    try:
        (temporary / "decision_inputs.jsonl").write_bytes(inputs_bytes)
        (temporary / "case_eligibility.jsonl").write_bytes(eligibility_bytes)
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        if output_dir.exists():
            raise ContractError(f"audit output already exists: {output_dir}")
        os.rename(temporary, output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return manifest
