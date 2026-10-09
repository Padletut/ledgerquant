"""Verified import of the two released offline attempts; never reads raw ticks."""

from hashlib import sha256
import json
from pathlib import Path

from .catalog import CATALOG, Diagnostic, develop


LEGACY_IDS = ("eurusd_four_hour_direction_2020_v1", "eurusd_four_hour_direction_2021_replication_v1")


def _read(path: Path, expected: str | None = None) -> tuple[bytes, str]:
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"required artifact unavailable: {path.name}") from exc
    digest = sha256(content).hexdigest()
    if expected is not None and digest != expected:
        raise ValueError(f"artifact hash mismatch: {path.name}")
    return content, digest


def _json(path, expected=None):
    content, digest = _read(path, expected)
    return json.loads(content), content.decode(), digest


def load_legacy_bundle(root: Path) -> dict:
    base = root / "documents/research"
    evidence, windows, attempts, development = [], [], [], None
    for hypothesis_id in LEGACY_IDS:
        freeze, _, _ = _json(base / "hypotheses" / f"{hypothesis_id}.freeze.json")
        contract, contract_text, contract_hash = _json(base / "hypotheses" / f"{hypothesis_id}.json", freeze["contract_sha256"])
        directory = base / "evaluations" / hypothesis_id
        seal, _, _ = _json(directory / "evaluation/evidence.freeze.json")
        result, original, result_hash = _json(directory / "evaluation/evidence.json", seal["evidence_sha256"])
        selection_seal, _, _ = _json(directory / "selection/selection.freeze.json")
        selection, _, selection_hash = _json(directory / "selection/selection.json", selection_seal["selection_sha256"])
        if result["hypothesis_id"] != hypothesis_id or result["contract_sha256"] != contract_hash or result["selection_sha256"] != selection_hash:
            raise ValueError("artifact lineage mismatch")
        if result["source_sha256"] != contract["feature_contract"]["source_sha256"]:
            raise ValueError("artifact source mismatch")
        _read(directory / "evaluation/validation_cases.jsonl", result["validation_cases_sha256"])
        content, dev_hash = _read(directory / "selection/development_cases.jsonl", selection["development_cases_sha256"])
        cases = [json.loads(line) for line in content.splitlines()]
        develop(Diagnostic(hours_utc=[8, 12, 16]), cases)
        if development is None:
            development = {"cases": cases, "artifact_sha256": dev_hash,
                           "start_inclusive_utc": CATALOG["development_start"],
                           "end_exclusive_utc": CATALOG["development_end"], "evidence_mode": "development"}
        elif development["artifact_sha256"] != dev_hash:
            raise ValueError("legacy attempts disagree on development snapshot")
        evidence.append({"id": hypothesis_id, "payload": result, "original": original, "sha256": result_hash})
        attempts.append({"id": hypothesis_id, "contract": contract_text, "contract_sha256": contract_hash,
                         "registered_at": freeze["registered_at_utc"], "parent_id": contract["parent_hypothesis_id"]})
        window = contract["validation_windows"][0]
        windows.append({"id": hypothesis_id, "state": "CONSUMED", "start": window["start_inclusive_utc"],
                        "end": window["end_exclusive_utc"], "first_access_at": result["evaluated_at_utc"],
                        "access_time_basis": "recorded_evaluation_time_prior_unrecorded_access_unknown"})
    source = {
        "source_id": contract["feature_contract"]["source_id"],
        "source_sha256": contract["feature_contract"]["source_sha256"],
        "instrument": "EURUSD", "visibility": "retrospective_assumed_server_quote_visibility",
        "historical_available_at": None, "cost_status": "COST_UNVERIFIED",
        "limitations": contract["data_sufficiency_policy"]["source_limitations"],
        "independent_windows": [],
    }
    return {"evidence": evidence, "windows": windows, "attempts": attempts,
            "development": development, "source": source}
