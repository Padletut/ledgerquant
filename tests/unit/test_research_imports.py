
import pytest

from ledgerquant.research.imports import load_legacy_bundle
from tests.private_evidence import REPO, private_evidence_root


def test_legacy_import_verifies_artifacts_and_retains_failed_replication():
    bundle = load_legacy_bundle(private_evidence_root())
    assert len(bundle["evidence"]) == 2
    assert bundle["evidence"][1]["payload"]["gate_decision"] == "TEMPORAL_FAILED"
    assert all(item["payload"]["related_trial_count"] == 1 for item in bundle["evidence"])
    assert all(item["state"] == "CONSUMED" for item in bundle["windows"])
    assert len(bundle["development"]["cases"]) == 390
    assert bundle["development"]["end_exclusive_utc"] == "2020-07-01T00:00:00Z"
    assert "source_file" not in str(bundle["source"])


def test_import_refuses_missing_artifact_without_substitution(tmp_path):
    with pytest.raises(ValueError, match="artifact"):
        load_legacy_bundle(tmp_path)


def test_import_refuses_public_redacted_artifacts():
    with pytest.raises(ValueError, match="hash mismatch"):
        load_legacy_bundle(REPO)
