"""Locate original, hash-verifiable research evidence kept outside public Git."""

import os
from pathlib import Path

import pytest


REPO = Path(__file__).parents[1]
LOCAL_BUNDLE = REPO / "data/private_publication_archive/account_redaction_20261010/verified_bundle"


def private_evidence_root() -> Path:
    root = Path(os.environ.get("LEDGERQUANT_PRIVATE_EVIDENCE_ROOT", LOCAL_BUNDLE))
    contract = root / "documents/research/hypotheses/eurusd_four_hour_direction_2020_v1.json"
    if not contract.is_file():
        pytest.skip("original research evidence is not available in this checkout")
    return root
