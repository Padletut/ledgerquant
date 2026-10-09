"""Verify and read the frozen inputs to offline selection and evaluation."""

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from .contracts import AuditContract, ContractError, load_frozen_contract


@dataclass(frozen=True)
class EvaluationData:
    contract: AuditContract
    spec: dict
    audit_dir: Path
    audit_manifest: dict
    audit_manifest_sha256: str

    def decision_inputs(self) -> list[dict]:
        return _jsonl(self.audit_dir / self.audit_manifest["decision_inputs_file"])

    def development_eligibility(self) -> list[dict]:
        """Stop before the first validation row is parsed."""
        rows = []
        path = self.audit_dir / self.audit_manifest["case_eligibility_file"]
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if b'"window":"validation"' in line.encode("utf-8"):
                    break
                row = json.loads(line)
                if row["window"] != "development":
                    raise ContractError("unexpected eligibility window order")
                rows.append(row)
        return rows

    def validation_eligibility(self) -> list[dict]:
        rows = _jsonl(self.audit_dir / self.audit_manifest["case_eligibility_file"])
        return [row for row in rows if row["window"] == "validation"]


def _jsonl(path: Path) -> list[dict]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"invalid JSONL artifact: {path.name}") from exc


def _verified_file(directory: Path, name: str, expected_sha256: str) -> Path:
    if Path(name).name != name:
        raise ContractError("artifact path escapes audit directory")
    path = directory / name
    try:
        actual = sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ContractError(f"cannot read artifact: {name}") from exc
    if actual != expected_sha256:
        raise ContractError(f"{name} SHA-256 mismatch")
    return path


def load_evaluation_data(
    repo_root: Path, freeze_path: Path, audit_dir: Path
) -> EvaluationData:
    root = repo_root.resolve()
    directory = audit_dir.resolve()
    if not directory.is_relative_to(root):
        raise ContractError("audit directory escapes repository root")
    contract = load_frozen_contract(root, freeze_path)
    freeze = json.loads(freeze_path.read_bytes())
    spec_path = (root / freeze["contract_path"]).resolve()
    if not spec_path.is_relative_to(root):
        raise ContractError("contract path escapes repository root")
    spec_bytes = spec_path.read_bytes()
    if sha256(spec_bytes).hexdigest() != contract.contract_sha256:
        raise ContractError("contract SHA-256 mismatch")
    spec = json.loads(spec_bytes)
    if spec["trial_budget"] != 1:
        raise ContractError("this evaluator supports one frozen trial")
    payoff = spec["payoff_contract"]
    if payoff["baseline"] != {
        "rule": "majority_development_target_class",
        "tie_class": "PREDICT_NON_UP",
    }:
        raise ContractError("unsupported baseline rule")
    if payoff["primary_metric"] != "paired_accuracy_difference_candidate_minus_baseline":
        raise ContractError("unsupported primary metric")
    uncertainty = payoff["uncertainty"]
    if uncertainty["method"] != "utc_date_block_bootstrap":
        raise ContractError("unsupported uncertainty method")
    if uncertainty["retain_all_anchors_per_sampled_date"] is not True:
        raise ContractError("unsupported bootstrap grouping")
    if not (type(uncertainty["resamples"]) is int and uncertainty["resamples"] > 0):
        raise ContractError("invalid resample count")
    if not (type(uncertainty["seed"]) is int and 0 < uncertainty["lower_percentile"] < 100):
        raise ContractError("invalid bootstrap policy")
    manifest_path = directory / "manifest.json"
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        if manifest["schema_version"] != 1 or manifest["hypothesis_id"] != contract.hypothesis_id:
            raise ContractError("audit manifest identity mismatch")
        if manifest["contract_sha256"] != contract.contract_sha256:
            raise ContractError("audit contract SHA-256 mismatch")
        if manifest["source_sha256"] != contract.source_sha256:
            raise ContractError("audit source SHA-256 mismatch")
        _verified_file(
            directory, manifest["decision_inputs_file"], manifest["decision_inputs_sha256"]
        )
        _verified_file(
            directory, manifest["case_eligibility_file"], manifest["case_eligibility_sha256"]
        )
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ContractError(f"invalid audit manifest: {exc}") from exc
    return EvaluationData(
        contract=contract,
        spec=spec,
        audit_dir=directory,
        audit_manifest=manifest,
        audit_manifest_sha256=sha256(manifest_bytes).hexdigest(),
    )
