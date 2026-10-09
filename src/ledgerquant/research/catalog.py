"""Versioned, finite catalog compiled from the existing price diagnostic."""

from collections import Counter
from datetime import datetime, timedelta
from typing import Literal

from pydantic import Field, StrictInt, field_validator

from .types import Record, digest


CATALOG = {
    "version": "eurusd_direction/1",
    "instrument": "EURUSD",
    "candidate_rule": "prior_hour_midquote_momentum_sign",
    "lookback_seconds": 3600,
    "horizon_seconds": 14400,
    "permitted_hours_utc": [8, 12, 16],
    "iso_weekdays": [1, 2, 3, 4, 5],
    "include_holidays": True,
    "baseline_rule": "majority_development_target_class",
    "baseline_tie": "PREDICT_NON_UP",
    "development_start": "2020-01-01T00:00:00Z",
    "development_end": "2020-07-01T00:00:00Z",
    "maximum_quote_age_seconds": 60,
    "maximum_settlement_delay_seconds": 60,
    "decision_delay_seconds": 1,
    "minimum_eligible_anchors": 100,
    "maximum_missing_fraction": 0.1,
    "orders_allowed": False,
    "economic_claim": "none_predictive_diagnostic_only",
    "validation_policy": "NO_INDEPENDENT_WINDOW",
    "inference_policy": "exploratory_only_no_confirmatory_pass",
    "search_policy": "one_declared_candidate_no_optimization",
}
FAMILY_ID = "eurusd_four_hour_direction"
CLASSES = {"PREDICT_UP", "PREDICT_NON_UP"}


class Diagnostic(Record):
    hours_utc: tuple[StrictInt, ...] = Field(min_length=1, max_length=3)
    catalog_version: Literal["eurusd_direction/1"] = "eurusd_direction/1"
    instrument: Literal["EURUSD"] = "EURUSD"
    candidate_rule: Literal["prior_hour_midquote_momentum_sign"] = "prior_hour_midquote_momentum_sign"
    lookback_seconds: Literal[3600] = 3600
    horizon_seconds: Literal[14400] = 14400
    orders_allowed: Literal[False] = False

    @field_validator("hours_utc")
    @classmethod
    def supported_hours(cls, hours):
        if list(hours) != sorted(set(hours)) or not set(hours) <= set(CATALOG["permitted_hours_utc"]):
            raise ValueError("hours must be a sorted subset of catalog hours")
        return hours


def classify(spec: Diagnostic) -> tuple[str, str, str]:
    """Names and model-suggested ancestry do not assign an independent family."""
    loop = "DUPLICATE" if list(spec.hours_utc) == CATALOG["permitted_hours_utc"] else "B"
    return FAMILY_ID, loop, digest(spec)


def develop(spec: Diagnostic, cases: list[dict]) -> dict:
    """Select the baseline from permitted, already materialized development rows."""
    start = datetime.fromisoformat(CATALOG["development_start"])
    end = datetime.fromisoformat(CATALOG["development_end"])
    selected, seen = [], set()
    for row in cases:
        anchor = datetime.fromisoformat(row["anchor_utc"])
        maturity = anchor + timedelta(seconds=spec.horizon_seconds + CATALOG["maximum_settlement_delay_seconds"])
        if anchor.utcoffset() != timedelta(0) or not start <= anchor < maturity < end:
            raise ValueError("development label crosses permitted boundary")
        if anchor.hour not in CATALOG["permitted_hours_utc"] or anchor.isoweekday() not in CATALOG["iso_weekdays"] or any((anchor.minute, anchor.second, anchor.microsecond)):
            raise ValueError("case is outside the registered anchor calendar")
        if row["case_id"] in seen:
            raise ValueError("duplicate development case")
        seen.add(row["case_id"])
        if row["status"] not in {"MEASURABLE", "INPUT_MISSING", "OUTCOME_MISSING"}:
            raise ValueError("unsupported case status")
        if row["status"] == "MEASURABLE" and (row["candidate"] not in CLASSES or row["target"] not in CLASSES):
            raise ValueError("measurable case lacks a supported label")
        if anchor.hour in spec.hours_utc:
            selected.append(row)
    measurable = [row for row in selected if row["status"] == "MEASURABLE"]
    counts = Counter(row["target"] for row in measurable)
    baseline = "PREDICT_UP" if counts["PREDICT_UP"] > counts["PREDICT_NON_UP"] else "PREDICT_NON_UP"
    n, total = len(measurable), len(selected)
    sufficient = n >= CATALOG["minimum_eligible_anchors"] and bool(total) and (total - n) / total <= CATALOG["maximum_missing_fraction"]
    return {
        "catalog_sha256": digest(CATALOG), "diagnostic_sha256": digest(spec),
        "evidence_mode": "development", "case_ids": [row["case_id"] for row in selected],
        "scheduled_count": total, "measurable_count": n,
        "case_status_counts": dict(Counter(row["status"] for row in selected)),
        "baseline_class": baseline,
        "candidate_accuracy": sum(row["candidate"] == row["target"] for row in measurable) / n if n else None,
        "baseline_accuracy": counts[baseline] / n if n else None,
        "data_sufficient": sufficient, "confirmatory_pass": None,
    }
