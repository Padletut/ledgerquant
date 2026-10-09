"""Run the offline eligibility audit for a frozen research contract."""

import argparse
from pathlib import Path

from .artifacts import publish_audit
from .audit import audit_cases
from .contracts import load_frozen_contract


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.repo_root.resolve()
    freeze = args.freeze if args.freeze.is_absolute() else root / args.freeze
    output = args.output_dir if args.output_dir.is_absolute() else root / args.output_dir
    contract = load_frozen_contract(root, freeze)
    manifest = publish_audit(audit_cases(contract, root), output)
    print(f"{output / 'manifest.json'}: {manifest['case_count']} cases")


if __name__ == "__main__":
    main()
