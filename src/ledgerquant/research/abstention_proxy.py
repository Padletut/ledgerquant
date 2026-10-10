"""Retrospective quote-only value of a synthetic XAUUSD abstention overlay."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from bisect import bisect_left
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median

from .quote_quality import _utc, evaluate_manifest


def estimate_intent(
    quotes: list[tuple[datetime, float, float]], anchor: datetime
) -> tuple[str, float] | None:
    """Estimate a synthetic 15-minute take value; None means no eligible intent."""
    times = [quote[0] for quote in quotes]
    old_at = bisect_left(times, anchor - timedelta(minutes=15)) - 1
    signal_at = bisect_left(times, anchor) - 1
    entry_at = bisect_left(times, anchor)
    exit_at = bisect_left(times, anchor + timedelta(minutes=15))
    if old_at < 0 or signal_at < 0 or exit_at >= len(quotes):
        return None
    old, signal, entry, exit_quote = (
        quotes[old_at], quotes[signal_at], quotes[entry_at], quotes[exit_at]
    )
    if (anchor - timedelta(minutes=15) - old[0] > timedelta(seconds=30)
            or anchor - signal[0] > timedelta(seconds=30)
            or entry[0] - anchor > timedelta(seconds=5)
            or exit_quote[0] - anchor - timedelta(minutes=15) > timedelta(seconds=5)):
        return None
    movement = (signal[1] + signal[2]) - (old[1] + old[2])
    if movement == 0:
        return ("TIE", 0.0)
    side = "LONG" if movement > 0 else "SHORT"
    value = exit_quote[1] - entry[2] if side == "LONG" else entry[1] - exit_quote[2]
    return side, round(value, 8)


def score_day(
    date_utc: str,
    cases: list[dict],
    quotes: list[tuple[datetime, float, float]],
    iqr_threshold: float,
    spread_threshold: float,
) -> dict:
    """Keep the same eligible intents in all three policies."""
    policies = {
        name: {"taken": 0, "skipped": 0, "quote_pnl_per_ounce": 0.0}
        for name in ("all_take", "iqr_overlay", "recent_spread_baseline")
    }
    scheduled = len(cases[1:-1])
    ineligible = tied = eligible = 0
    for previous, current in zip(cases[:-2], cases[1:-1]):
        if previous["status"] != "MEASURABLE" or current["status"] != "MEASURABLE":
            ineligible += 1
            continue
        anchor = _utc(current["anchor_utc"])
        if anchor - _utc(previous["anchor_utc"]) != timedelta(minutes=15):
            raise ValueError("Nonconsecutive quote-quality cases")
        intent = estimate_intent(quotes, anchor)
        if intent is None:
            ineligible += 1
            continue
        side, value = intent
        if side == "TIE":
            tied += 1
            continue
        eligible += 1
        skip_iqr = current["lookback_spread_iqr"] > iqr_threshold
        skip_spread = previous["forward_spread_p95"] > spread_threshold
        for name, skip in (("all_take", False), ("iqr_overlay", skip_iqr),
                           ("recent_spread_baseline", skip_spread)):
            policy = policies[name]
            policy["skipped" if skip else "taken"] += 1
            if not skip:
                policy["quote_pnl_per_ounce"] = round(policy["quote_pnl_per_ounce"] + value, 8)
    if eligible + ineligible + tied != scheduled:
        raise AssertionError("Scheduled anchors were not fully accounted for")
    return {
        "date_utc": date_utc,
        "scheduled_anchors": scheduled,
        "eligible_intents": eligible,
        "ineligible_anchors": ineligible,
        "tied_signal_anchors": tied,
        **policies,
        "iqr_minus_all_take_per_ounce": round(
            policies["iqr_overlay"]["quote_pnl_per_ounce"] - policies["all_take"]["quote_pnl_per_ounce"], 8
        ),
        "iqr_minus_recent_spread_per_ounce": round(
            policies["iqr_overlay"]["quote_pnl_per_ounce"]
            - policies["recent_spread_baseline"]["quote_pnl_per_ounce"], 8
        ),
    }


def _read_quotes(manifest_path: Path) -> list[tuple[datetime, float, float]]:
    manifest = json.loads(manifest_path.read_text())
    quotes = []
    with (manifest_path.parent / manifest["data_file"]).open(newline="") as source:
        for row in csv.DictReader(source):
            quotes.append((_utc(row["event_time_utc"]), float(row["bid"]), float(row["ask"])))
    return quotes


def measure(design_path: Path, exports: Path, cases_path: Path) -> dict:
    design_bytes = design_path.read_bytes()
    design = json.loads(design_bytes)
    if design["status"] != "RETROSPECTIVE_DEVELOPMENT_DESIGN":
        raise ValueError("Unsupported measurement design")
    dates = design["dates_utc"]
    if len(dates) != 6 or len(set(dates)) != 6 or any(not day.startswith("2020-") for day in dates):
        raise ValueError("Unexpected development dates")
    case_bytes = cases_path.read_bytes()
    if hashlib.sha256(case_bytes).hexdigest() != design["case_artifact_sha256"]:
        raise ValueError("Quote-quality case artifact changed")
    recorded = json.loads(case_bytes)
    if [day["date_utc"] for day in recorded["days"]] != dates:
        raise ValueError("Case dates differ from design")
    iqr_values = [case["lookback_spread_iqr"] for day in recorded["days"]
                  for case in day["cases"] if case["status"] == "MEASURABLE"]
    spread_values = [day["cases"][i - 1]["forward_spread_p95"] for day in recorded["days"]
                     for i in range(1, len(day["cases"]))]
    thresholds = design["thresholds_usd_per_ounce"]
    iqr_threshold = thresholds["prior_30m_spread_iqr"]
    spread_threshold = thresholds["previous_15m_spread_p95"]
    if abs(median(iqr_values) - iqr_threshold) > 1e-8 or abs(median(spread_values) - spread_threshold) > 1e-8:
        raise ValueError("Feature thresholds differ from declared development medians")
    first_manifest = json.loads((exports / f"xauusd_{dates[0]}-quote-dev-v1.manifest.json").read_text())
    account_number = first_manifest["account_number"]  # private identity check; never emitted
    days = []
    for day in dates:
        manifest_path = exports / f"xauusd_{day}-quote-dev-v1.manifest.json"
        verified = evaluate_manifest(manifest_path, day, account_number)
        recorded_day = next(item for item in recorded["days"] if item["date_utc"] == day)
        if verified != recorded_day:
            raise ValueError("Recomputed source cases differ from the recorded artifact")
        days.append(score_day(day, verified["cases"], _read_quotes(manifest_path),
                              iqr_threshold, spread_threshold))
    totals = {
        key: sum(day[key] for day in days)
        for key in ("scheduled_anchors", "eligible_intents", "ineligible_anchors", "tied_signal_anchors")
    }
    for name in ("all_take", "iqr_overlay", "recent_spread_baseline"):
        totals[name] = {
            key: round(sum(day[name][key] for day in days), 8)
            for key in ("taken", "skipped", "quote_pnl_per_ounce")
        }
    totals["iqr_minus_all_take_per_ounce"] = round(
        totals["iqr_overlay"]["quote_pnl_per_ounce"] - totals["all_take"]["quote_pnl_per_ounce"], 8
    )
    totals["iqr_minus_recent_spread_per_ounce"] = round(
        totals["iqr_overlay"]["quote_pnl_per_ounce"]
        - totals["recent_spread_baseline"]["quote_pnl_per_ounce"], 8
    )
    return {
        "mode": "RETROSPECTIVE_DEVELOPMENT_QUOTE_PROXY",
        "design_sha256": hashlib.sha256(design_bytes).hexdigest(),
        "measurement_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "case_artifact_sha256": hashlib.sha256(case_bytes).hexdigest(),
        "days": days,
        "totals": totals,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("design", type=Path)
    parser.add_argument("exports", type=Path)
    parser.add_argument("cases", type=Path)
    args = parser.parse_args()
    print(json.dumps(measure(args.design, args.exports, args.cases), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
