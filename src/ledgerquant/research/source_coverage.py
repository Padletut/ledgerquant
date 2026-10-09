"""Measure quote presence and source integrity without research outcomes."""

from collections import Counter, defaultdict
from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path

from .audit import _iso, _parse_source_row
from .contracts import ContractError


def scan_source_window(
    source: Path, expected_sha256: str, start: date, end: date
) -> dict:
    """Hash the full source and characterize only rows in [start, end)."""
    if start >= end:
        raise ContractError("coverage start must precede end")
    first_day = start.isoformat().encode("ascii")
    after_last_day = end.isoformat().encode("ascii")
    digest = sha256()
    source_bytes = 0
    rows_in_scope = 0
    identical_bid_ask_rows = 0
    equal_timestamp_rows = 0
    observed_days: set[date] = set()
    monthly_rows: Counter[str] = Counter()
    monthly_days: dict[str, set[date]] = defaultdict(set)
    cached_day = None
    day_ms = 0
    previous_event_ms = None
    first_event_ms = None
    last_event_ms = None
    try:
        with source.open("rb") as handle:
            for line_number, raw in enumerate(handle, 1):
                digest.update(raw)
                source_bytes += len(raw)
                day = raw[:10]
                if not first_day <= day < after_last_day:
                    continue
                cached_day, day_ms, event_ms, _ = _parse_source_row(
                    raw, line_number, cached_day, day_ms
                )
                if previous_event_ms is not None:
                    if event_ms < previous_event_ms:
                        raise ContractError(f"timestamp reversal at source line {line_number}")
                    equal_timestamp_rows += event_ms == previous_event_ms
                previous_event_ms = event_ms
                if first_event_ms is None:
                    first_event_ms = event_ms
                last_event_ms = event_ms
                rows_in_scope += 1
                current_day = date.fromisoformat(day.decode("ascii"))
                observed_days.add(current_day)
                month = day[:7].decode("ascii")
                monthly_rows[month] += 1
                monthly_days[month].add(current_day)
                fields = raw.rstrip(b"\r\n").split(b",")
                identical_bid_ask_rows += fields[2] == fields[3]
    except OSError as exc:
        raise ContractError(f"cannot read source: {exc}") from exc
    if digest.hexdigest() != expected_sha256:
        raise ContractError("source SHA-256 mismatch")

    missing_weekdays = []
    day = start
    while day < end:
        if day.isoweekday() <= 5 and day not in observed_days:
            missing_weekdays.append(day.isoformat())
        day += timedelta(days=1)
    return {
        "schema_version": 1,
        "measurement_type": "source_presence_without_research_outcomes",
        "source_sha256": expected_sha256,
        "source_bytes": source_bytes,
        "start_inclusive_utc": start.isoformat() + "T00:00:00Z",
        "end_exclusive_utc": end.isoformat() + "T00:00:00Z",
        "rows_in_scope": rows_in_scope,
        "observed_utc_dates": len(observed_days),
        "first_event_at_utc": None if first_event_ms is None else _iso(first_event_ms),
        "last_event_at_utc": None if last_event_ms is None else _iso(last_event_ms),
        "weekday_dates_without_rows": missing_weekdays,
        "identical_bid_ask_rows": identical_bid_ask_rows,
        "equal_timestamp_rows": equal_timestamp_rows,
        "monthly_presence": {
            month: {"rows": monthly_rows[month], "observed_utc_dates": len(monthly_days[month])}
            for month in sorted(monthly_rows)
        },
        "contains_predictions_or_outcomes": False,
    }
