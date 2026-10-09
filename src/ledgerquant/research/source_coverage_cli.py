"""Publish a source-backed presence report before validating a new period."""

import argparse
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from .contracts import load_frozen_contract
from .immutable import publish_directory
from .source_coverage import scan_source_window


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--source-contract-freeze", type=Path, required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.repo_root.resolve()
    freeze = args.source_contract_freeze
    freeze = freeze if freeze.is_absolute() else root / freeze
    output = args.output_dir
    output = output if output.is_absolute() else root / output
    contract = load_frozen_contract(root, freeze)
    report = scan_source_window(contract.source_file, contract.source_sha256, args.start, args.end)
    digest = sha256()
    for name in ("source_coverage.py", "audit.py"):
        digest.update(name.encode("ascii") + b"\0" + Path(__file__).with_name(name).read_bytes())
    report.update(
        source_id=contract.source_id,
        source_file=str(contract.source_file.relative_to(root)),
        source_contract_sha256=contract.contract_sha256,
        measurement_code_sha256=digest.hexdigest(),
        generated_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    )
    payload = (json.dumps(report, indent=2) + "\n").encode("utf-8")
    publish_directory(output, {"coverage.json": payload})
    print(f"{output / 'coverage.json'}: {report['rows_in_scope']} rows")


if __name__ == "__main__":
    main()
