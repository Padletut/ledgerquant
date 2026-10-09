"""Frozen predictive metrics and daily block uncertainty for one diagnostic."""

from collections import Counter, defaultdict
from decimal import Decimal
import math
import random

from .contracts import Window


def bootstrap_lower_bound(
    rows: list[dict], resamples: int, seed: int, percentile: int
) -> float | None:
    if not rows:
        return None
    by_day = defaultdict(lambda: [0, 0])
    for row in rows:
        day = row["anchor_utc"][:10]
        by_day[day][0] += int(row["candidate_correct"]) - int(row["baseline_correct"])
        by_day[day][1] += 1
    days = [by_day[day] for day in sorted(by_day)]
    rng = random.Random(seed)
    draws = []
    for _ in range(resamples):
        sampled = [days[rng.randrange(len(days))] for _ in days]
        draws.append(sum(item[0] for item in sampled) / sum(item[1] for item in sampled))
    draws.sort()
    return draws[max(0, math.ceil(percentile / 100 * resamples) - 1)]


def _accuracy(rows: list[dict], field: str) -> float | None:
    return sum(bool(row[field]) for row in rows) / len(rows) if rows else None


def _quarter(anchor_utc: str) -> str:
    return f"{anchor_utc[:4]}Q{(int(anchor_utc[5:7]) - 1) // 3 + 1}"


def summarize_validation(
    cases: list[dict],
    window: Window,
    maximum_unmeasurable_fraction: float,
    uncertainty: dict,
) -> tuple[dict, str, str | None]:
    measurable = [row for row in cases if row["status"] == "MEASURABLE"]
    candidate_accuracy = _accuracy(measurable, "candidate_correct")
    baseline_accuracy = _accuracy(measurable, "baseline_correct")
    paired = (
        candidate_accuracy - baseline_accuracy
        if candidate_accuracy is not None and baseline_accuracy is not None else None
    )
    lower = bootstrap_lower_bound(
        measurable,
        uncertainty["resamples"],
        uncertainty["seed"],
        uncertainty["lower_percentile"],
    )
    counts = Counter(row["status"] for row in cases)
    support_ok = counts["MEASURABLE"] >= window.minimum_eligible_anchors
    missing_ok = (
        bool(cases)
        and (len(cases) - counts["MEASURABLE"]) / len(cases)
        <= maximum_unmeasurable_fraction
    )
    if not support_ok:
        gate_decision, failure_reason = "INSUFFICIENT_SUPPORT", "INSUFFICIENT_SUPPORT"
    elif not missing_ok:
        gate_decision, failure_reason = "DATA_QUALITY_FAILED", "DATA_QUALITY_FAILURE"
    elif lower is None or lower <= 0:
        gate_decision, failure_reason = "TEMPORAL_FAILED", "TEMPORAL_FAILURE"
    else:
        gate_decision, failure_reason = "PREDICTIVE_VALIDATION_PASSED", None

    quarters = {}
    for quarter in sorted({_quarter(row["anchor_utc"]) for row in measurable}):
        subset = [row for row in measurable if _quarter(row["anchor_utc"]) == quarter]
        quarter_candidate = _accuracy(subset, "candidate_correct")
        quarter_baseline = _accuracy(subset, "baseline_correct")
        quarters[quarter] = {
            "count": len(subset),
            "candidate_accuracy": quarter_candidate,
            "baseline_accuracy": quarter_baseline,
            "paired_accuracy_difference": quarter_candidate - quarter_baseline,
        }
    forward_by_class = {}
    for predicted_class in ("PREDICT_UP", "PREDICT_NON_UP"):
        subset = [row for row in measurable if row["candidate"] == predicted_class]
        forward_by_class[predicted_class] = {
            "count": len(subset),
            "mean_midquote_change": (
                format(
                    sum(Decimal(row["forward_midquote_change"]) for row in subset)
                    / len(subset),
                    "f",
                ) if subset else None
            ),
        }
    summary = {
        "scheduled_count": len(cases),
        "measurable_count": len(measurable),
        "case_status_counts": dict(counts),
        "candidate_accuracy": candidate_accuracy,
        "baseline_accuracy": baseline_accuracy,
        "paired_accuracy_difference": paired,
        "bootstrap_lower_bound": lower,
        "bootstrap_method": uncertainty["method"],
        "bootstrap_resamples": uncertainty["resamples"],
        "bootstrap_seed": uncertainty["seed"],
        "bootstrap_percentile": uncertainty["lower_percentile"],
        "bootstrap_percentile_convention": "nearest_rank",
        "quarters": quarters,
        "forward_midquote_change_by_prediction": forward_by_class,
        "minimum_support_met": support_ok,
        "maximum_missingness_met": bool(missing_ok),
    }
    return summary, gate_decision, failure_reason
