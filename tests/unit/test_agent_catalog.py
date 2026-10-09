from copy import deepcopy

import pytest
from pydantic import ValidationError

from ledgerquant.research.catalog import CATALOG, Diagnostic, classify, develop
from ledgerquant.research.proposals import Proposal


def proposal_payload():
    return {
        "title": "Morning-only EURUSD diagnostic",
        "diagnostic": {"hours_utc": [8]},
        "mechanism": "Test whether the registered price rule differs by decision hour.",
        "support": ["The released rule did not transport to 2021."],
        "contrary_evidence": ["The earlier full-day rule failed temporal validation."],
        "falsifier": "No improvement against the frozen baseline on new evidence.",
        "predicted_failure": "TEMPORAL_FAILURE",
        "admissibility_probability": 0.5,
        "evidence_ids": ["eurusd_four_hour_direction_2021_replication_v1"],
        "data_requirements": [],
    }


def test_catalog_matches_reviewed_rule_and_rejects_unsupported_semantics():
    assert CATALOG["horizon_seconds"] == 14400
    assert Diagnostic(hours_utc=[8]).hours_utc == (8,)
    for change in ({"horizon_seconds": 10800}, {"hours_utc": [9]}, {"hours_utc": [8, 8]},
                   {"candidate_rule": "return_positive"}, {"orders_allowed": True}):
        with pytest.raises(ValidationError):
            Diagnostic.model_validate({"hours_utc": [8], **change})


def test_proposer_cannot_choose_family_write_measurements_or_success():
    for key, value in (("family_id", "brand-new"), ("net_expectancy", 2.0),
                       ("success_gate", "always pass"), ("status", "PROMOTED")):
        with pytest.raises(ValidationError):
            Proposal.model_validate({**proposal_payload(), key: value})


def test_renaming_cannot_reset_identity_and_new_timing_stays_related():
    first = Proposal.model_validate(proposal_payload())
    renamed = first.model_copy(update={"title": "Totally new discovery"})
    assert classify(first.diagnostic) == classify(renamed.diagnostic)
    assert classify(first.diagnostic)[0] == "eurusd_four_hour_direction"
    assert classify(first.diagnostic)[1] == "B"
    assert classify(Diagnostic(hours_utc=[8, 12, 16]))[1] == "DUPLICATE"


def test_development_baseline_uses_selected_hours_and_retains_missing():
    cases = [
        {"case_id": "a", "anchor_utc": "2020-01-02T08:00:00Z", "status": "MEASURABLE", "candidate": "PREDICT_UP", "target": "PREDICT_UP"},
        {"case_id": "b", "anchor_utc": "2020-01-02T12:00:00Z", "status": "MEASURABLE", "candidate": "PREDICT_NON_UP", "target": "PREDICT_NON_UP"},
        {"case_id": "c", "anchor_utc": "2020-01-03T08:00:00Z", "status": "INPUT_MISSING", "candidate": None, "target": None},
    ]
    result = develop(Diagnostic(hours_utc=[8]), cases)
    assert result["baseline_class"] == "PREDICT_UP"
    assert result["scheduled_count"] == 2
    assert result["measurable_count"] == 1
    assert result["case_ids"] == ["a", "c"]
    assert result["evidence_mode"] == "development"
    assert result["confirmatory_pass"] is None


def test_development_rejects_future_labels_duplicate_cases_and_unknown_status():
    row = {"case_id": "a", "anchor_utc": "2020-06-30T23:00:00Z", "status": "MEASURABLE", "candidate": "PREDICT_UP", "target": "PREDICT_UP"}
    with pytest.raises(ValueError, match="boundary"):
        develop(Diagnostic(hours_utc=[8]), [row])
    row["anchor_utc"] = "2020-01-02T08:00:00Z"
    with pytest.raises(ValueError, match="duplicate"):
        develop(Diagnostic(hours_utc=[8]), [row, deepcopy(row)])
    row["status"] = "DROP_BAD_TRADE"
    with pytest.raises(ValueError, match="status"):
        develop(Diagnostic(hours_utc=[8]), [row])
