"""Offline XAUUSD development diagnostic for a broker backfill quote stream."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("Expected a UTC timestamp")
    return parsed


def _percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    low = int(position)
    remainder = position - low
    return round(ordered[low] + (ordered[min(low + 1, len(ordered) - 1)] - ordered[low]) * remainder, 8)


def measure_windows(
    ticks: list[tuple[datetime, float]], start: datetime, anchors: list[datetime]
) -> list[dict]:
    """Sample last known quotes at 1 Hz; never borrow a quote from the future."""
    if not ticks or any(ticks[i][0] > ticks[i + 1][0] for i in range(len(ticks) - 1)):
        raise ValueError("Ticks must be nonempty and ordered")
    end = max(anchors) + timedelta(minutes=15)
    seconds = int((end - start).total_seconds())
    samples: list[float | None] = []
    next_tick = 0
    last_time: datetime | None = None
    last_spread = 0.0
    for offset in range(seconds):
        sample_time = start + timedelta(seconds=offset)
        while next_tick < len(ticks) and ticks[next_tick][0] <= sample_time:
            last_time, last_spread = ticks[next_tick]
            next_tick += 1
        age = (sample_time - last_time).total_seconds() if last_time else float("inf")
        samples.append(last_spread if age <= 30 else None)

    cases = []
    for anchor in anchors:
        index = int((anchor - start).total_seconds())
        if index < 1800 or index + 900 > len(samples):
            raise ValueError("Anchor lies outside the complete 30/15-minute sample window")
        past = samples[index - 1800:index]
        future = samples[index:index + 900]
        case = {
            "anchor_utc": anchor.isoformat().replace("+00:00", "Z"),
            "status": "MEASURABLE",
            "lookback_spread_iqr": None,
            "forward_spread_p95": None,
        }
        if None in past or None in future:
            case["status"] = "INSUFFICIENT_SOURCE"
        else:
            case["lookback_spread_iqr"] = round(_percentile(past, 0.75) - _percentile(past, 0.25), 8)
            case["forward_spread_p95"] = _percentile(future, 0.95)
        cases.append(case)
    return cases


def _ranks(values: list[float]) -> list[float]:
    ranked = sorted(enumerate(values), key=lambda pair: round(pair[1], 8))
    result = [0.0] * len(values)
    i = 0
    while i < len(ranked):
        j = i + 1
        while j < len(ranked) and round(ranked[j][1], 8) == round(ranked[i][1], 8):
            j += 1
        for k in range(i, j):
            result[ranked[k][0]] = (i + j - 1) / 2
        i = j
    return result


def _spearman_values(first: list[float], second: list[float]) -> float | None:
    if len(first) != len(second):
        raise ValueError("Rank vectors must have equal length")
    if len(first) < 2:
        return None
    x = _ranks(first)
    y = _ranks(second)
    xmean, ymean = sum(x) / len(x), sum(y) / len(y)
    numerator = sum((a - xmean) * (b - ymean) for a, b in zip(x, y))
    xss = sum((a - xmean) ** 2 for a in x)
    yss = sum((b - ymean) ** 2 for b in y)
    return numerator / (xss * yss) ** 0.5 if xss and yss else None


def _spearman(cases: list[dict]) -> float | None:
    measurable = [case for case in cases if case["status"] == "MEASURABLE"]
    return _spearman_values(
        [case["lookback_spread_iqr"] for case in measurable],
        [case["forward_spread_p95"] for case in measurable],
    )


def compare_recent_spread_baseline(cases: list[dict]) -> dict:
    """Compare prior 30-minute IQR with the preceding 15-minute p95 on paired anchors."""
    proposed: list[float] = []
    baseline: list[float] = []
    outcomes: list[float] = []
    for previous, current in zip(cases, cases[1:]):
        if _utc(current["anchor_utc"]) - _utc(previous["anchor_utc"]) != timedelta(minutes=15):
            raise ValueError("Baseline requires consecutive 15-minute anchors")
        if previous["status"] != "MEASURABLE" or current["status"] != "MEASURABLE":
            continue
        proposed.append(current["lookback_spread_iqr"])
        baseline.append(previous["forward_spread_p95"])
        outcomes.append(current["forward_spread_p95"])
    proposed_rho = _spearman_values(proposed, outcomes)
    baseline_rho = _spearman_values(baseline, outcomes)
    return {
        "paired_cases": len(outcomes),
        "iqr_spearman": proposed_rho,
        "recent_spread_spearman": baseline_rho,
        "delta_iqr_minus_recent_spread": (
            proposed_rho - baseline_rho
            if proposed_rho is not None and baseline_rho is not None else None
        ),
    }


def evaluate_manifest(manifest_path: Path, day: str, expected_account_number: int | None = None) -> dict:
    manifest = json.loads(manifest_path.read_text())
    expected_start = _utc(f"{day}T07:30:00Z")
    expected_end = _utc(f"{day}T16:15:00Z")
    required = {
        "source_type": "broker_historical_tick_backfill",
        "broker_name": "IC Markets EU Ltd",
        "account_environment": "live",
        "broker_symbol": "XAUUSD",
        "data_mode": "ctrader_cli_server_ticks",
    }
    if any(manifest.get(key) != value for key, value in required.items()):
        raise ValueError("Unexpected source identity")
    account_number = manifest.get("account_number")
    if (not isinstance(account_number, int) or isinstance(account_number, bool) or account_number <= 0
            or (expected_account_number is not None and account_number != expected_account_number)):
        raise ValueError("Unexpected source account")
    if (_utc(manifest["requested_start_utc"]), _utc(manifest["requested_end_exclusive_utc"])) != (expected_start, expected_end):
        raise ValueError("Unexpected export window")
    data_file = Path(manifest["data_file"])
    if data_file.name != str(data_file):
        raise ValueError("Data file must be local to its manifest")
    data_path = manifest_path.parent / data_file
    raw = data_path.read_bytes()
    if len(raw) != manifest["data_bytes"] or hashlib.sha256(raw).hexdigest() != manifest["data_sha256"]:
        raise ValueError("Data hash or byte length mismatch")

    ticks: list[tuple[datetime, float]] = []
    with data_path.open(newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != ["ordinal", "event_time_utc", "bid", "ask"]:
            raise ValueError("Unexpected CSV columns")
        for expected_ordinal, row in enumerate(reader, 1):
            event_time = _utc(row["event_time_utc"])
            bid, ask = Decimal(row["bid"]), Decimal(row["ask"])
            if (int(row["ordinal"]) != expected_ordinal or not expected_start <= event_time < expected_end
                    or (ticks and event_time < ticks[-1][0]) or not bid.is_finite()
                    or not ask.is_finite() or bid <= 0 or ask < bid):
                raise ValueError("Invalid quote, order or event time")
            ticks.append((event_time, float(ask - bid)))
    if len(ticks) != manifest["row_count"] or not ticks:
        raise ValueError("Row count mismatch")
    if (_utc(manifest["first_event_utc"]), _utc(manifest["last_event_utc"])) != (ticks[0][0], ticks[-1][0]):
        raise ValueError("Manifest event bounds mismatch")
    duplicates = sum(ticks[i][0] == ticks[i - 1][0] for i in range(1, len(ticks)))
    zero_spreads = sum(spread == 0 for _, spread in ticks)
    if duplicates != manifest["duplicate_timestamps"] or zero_spreads != manifest["zero_spread_rows"]:
        raise ValueError("Manifest quote counts mismatch")

    first_anchor = _utc(f"{day}T08:15:00Z")
    anchors = [first_anchor + timedelta(minutes=15 * index) for index in range(32)]
    cases = measure_windows(ticks, expected_start, anchors)
    return {
        "date_utc": day,
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "data_sha256": manifest["data_sha256"],
        "source_rows": len(ticks),
        "measurable_cases": sum(case["status"] == "MEASURABLE" for case in cases),
        "insufficient_source_cases": sum(case["status"] == "INSUFFICIENT_SOURCE" for case in cases),
        "spearman_within_day": _spearman(cases),
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sampling", type=Path)
    parser.add_argument("exports", type=Path)
    args = parser.parse_args()
    plan = json.loads(args.sampling.read_text())
    dates = plan["development_dates_utc"]
    if any(not day.startswith("2020-") for day in dates):
        raise ValueError("This command permits only the declared 2020 development dates")
    first_manifest = json.loads((args.exports / f"xauusd_{dates[0]}-quote-dev-v1.manifest.json").read_text())
    account_number = first_manifest.get("account_number")
    results = [evaluate_manifest(args.exports / f"xauusd_{day}-quote-dev-v1.manifest.json", day, account_number) for day in dates]
    print(json.dumps({
        "mode": "RETROSPECTIVE_DEVELOPMENT_DESCRIPTIVE",
        "sampling_sha256": hashlib.sha256(args.sampling.read_bytes()).hexdigest(),
        "days": results,
    }, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
