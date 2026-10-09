"""Prepare a frozen candidate, then run its separate offline evaluator."""

import argparse
from pathlib import Path

from .evaluator import evaluate_selection
from .selection import prepare_selection


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "evaluate"))
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--audit-dir", type=Path, required=True)
    parser.add_argument("--selection-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    root = args.repo_root.resolve()

    def under_root(path: Path) -> Path:
        return path if path.is_absolute() else root / path

    freeze = under_root(args.freeze)
    audit = under_root(args.audit_dir)
    selection = under_root(args.selection_dir)
    if args.phase == "prepare":
        if args.output_dir is not None:
            parser.error("--output-dir belongs to the evaluate phase")
        result = prepare_selection(root, freeze, audit, selection)
        print(f"{selection / 'selection.json'}: {result['selection_status']}")
    else:
        if args.output_dir is None:
            parser.error("--output-dir is required for evaluation")
        output = under_root(args.output_dir)
        result = evaluate_selection(root, freeze, audit, selection, output)
        print(f"{output / 'evidence.json'}: {result['gate_decision']}")


if __name__ == "__main__":
    main()
