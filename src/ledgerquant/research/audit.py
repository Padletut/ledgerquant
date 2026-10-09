"""Source-backed eligibility audit without predictions or outcome prices."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path

from .contracts import AuditContract, ContractError


EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
DAY_MS = 86_400_000


@dataclass(frozen=True)
class SourceRef:
    event_ms: int
    source_line: int
    midquote: Decimal


@dataclass(frozen=True)
class Anchor:
    window: str
    at: datetime
    event_ms: int


@dataclass(frozen=True)
class CaseAudit:
    contract: AuditContract
    cases: tuple[dict, ...]
    source_bytes: int
    source_rows_in_scope: int


def _event_ms(value: datetime) -> int:
    delta = value - EPOCH
    return delta.days * DAY_MS + delta.seconds * 1000 + delta.microseconds // 1000


def _iso(event_ms: int) -> str:
    return (EPOCH + timedelta(milliseconds=event_ms)).isoformat().replace("+00:00", "Z")


def _anchors(contract: AuditContract) -> tuple[Anchor, ...]:
    result = []
    for window in contract.windows:
        current = window.start.date()
        while current < window.end.date():
            if current.isoweekday() in contract.iso_weekdays:
                for hour in contract.hours_utc:
                    at = datetime(current.year, current.month, current.day, hour, tzinfo=timezone.utc)
                    if window.start <= at < window.end:
                        result.append(Anchor(window.name, at, _event_ms(at)))
            current += timedelta(days=1)
    return tuple(result)


def _parse_source_row(raw: bytes, line_number: int, cached_day: bytes | None, day_ms: int):
    fields = raw.rstrip(b"\r\n").split(b",")
    if len(fields) != 4:
        raise ContractError(f"malformed row at source line {line_number}")
    day, clock, bid_raw, ask_raw = fields
    if day != cached_day:
        try:
            parsed_day = date.fromisoformat(day.decode("ascii"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise ContractError(f"malformed row at source line {line_number}") from exc
        day_ms = (parsed_day.toordinal() - date(1970, 1, 1).toordinal()) * DAY_MS
    if len(clock) != 12 or clock[2:3] != b":" or clock[5:6] != b":" or clock[8:9] != b".":
        raise ContractError(f"malformed row at source line {line_number}")
    if not (
        clock[:2].isdigit()
        and clock[3:5].isdigit()
        and clock[6:8].isdigit()
        and clock[9:12].isdigit()
    ):
        raise ContractError(f"malformed row at source line {line_number}")
    try:
        hour = int(clock[:2])
        minute = int(clock[3:5])
        second = int(clock[6:8])
        millis = int(clock[9:12])
        bid = Decimal(bid_raw.decode("ascii"))
        ask = Decimal(ask_raw.decode("ascii"))
    except (UnicodeDecodeError, ValueError, InvalidOperation) as exc:
        raise ContractError(f"malformed row at source line {line_number}") from exc
    if hour > 23 or minute > 59 or second > 59 or millis > 999:
        raise ContractError(f"malformed row at source line {line_number}")
    if not bid.is_finite() or not ask.is_finite() or bid <= 0 or ask <= 0:
        raise ContractError(f"nonpositive quote at source line {line_number}")
    if ask < bid:
        raise ContractError(f"crossed quote at source line {line_number}")
    return day, day_ms, day_ms + ((hour * 60 + minute) * 60 + second) * 1000 + millis, (bid + ask) / 2


def _source_refs(contract: AuditContract, anchors: tuple[Anchor, ...]):
    inputs = sorted(
        (
            target,
            case_index,
            role,
        )
        for case_index, anchor in enumerate(anchors)
        for role, target in enumerate(
            (anchor.event_ms - contract.lookback_seconds * 1000, anchor.event_ms)
        )
    )
    settlements = sorted(
        (anchor.event_ms + contract.settlement_horizon_seconds * 1000, index)
        for index, anchor in enumerate(anchors)
    )
    input_refs: list[list[SourceRef | None]] = [[None, None] for _ in anchors]
    settlement_refs: list[SourceRef | None] = [None for _ in anchors]
    first_day = contract.windows[0].start.date().isoformat().encode("ascii")
    after_last_day = contract.windows[-1].end.date().isoformat().encode("ascii")
    source_hash = sha256()
    source_bytes = 0
    rows_in_scope = 0
    cached_day = None
    day_ms = 0
    last_event_ms = None
    last_ref = None
    input_index = 0
    settlement_index = 0

    try:
        with contract.source_file.open("rb") as source:
            for line_number, raw in enumerate(source, 1):
                source_hash.update(raw)
                source_bytes += len(raw)
                if not first_day <= raw[:10] < after_last_day:
                    continue
                cached_day, day_ms, event_ms, midquote = _parse_source_row(raw, line_number, cached_day, day_ms)
                rows_in_scope += 1
                if last_event_ms is not None and event_ms < last_event_ms:
                    raise ContractError(f"timestamp reversal at source line {line_number}")
                while input_index < len(inputs) and inputs[input_index][0] < event_ms:
                    _, case_index, role = inputs[input_index]
                    input_refs[case_index][role] = last_ref
                    input_index += 1
                current_ref = SourceRef(event_ms, line_number, midquote)
                while settlement_index < len(settlements) and settlements[settlement_index][0] <= event_ms:
                    _, case_index = settlements[settlement_index]
                    settlement_refs[case_index] = current_ref
                    settlement_index += 1
                last_ref = current_ref
                last_event_ms = event_ms
    except OSError as exc:
        raise ContractError(f"cannot read source: {exc}") from exc

    if source_hash.hexdigest() != contract.source_sha256:
        raise ContractError("source SHA-256 mismatch")
    while input_index < len(inputs):
        _, case_index, role = inputs[input_index]
        input_refs[case_index][role] = last_ref
        input_index += 1
    return input_refs, settlement_refs, source_bytes, rows_in_scope


def _input_record(ref: SourceRef | None, target_ms: int, maximum_age_ms: int) -> dict:
    age = None if ref is None else target_ms - ref.event_ms
    eligible = age is not None and 0 <= age <= maximum_age_ms
    return {
        "source_line": None if ref is None else ref.source_line,
        "event_at_utc": None if ref is None else _iso(ref.event_ms),
        "age_ms": age,
        "eligible": eligible,
        "midquote": format(ref.midquote, "f") if eligible else None,
    }


def _settlement_record(ref: SourceRef | None, target_ms: int, maximum_delay_ms: int) -> dict:
    delay = None if ref is None else ref.event_ms - target_ms
    return {
        "event_at_utc": None if ref is None else _iso(ref.event_ms),
        "delay_ms": delay,
        "eligible": delay is not None and 0 <= delay <= maximum_delay_ms,
    }


def audit_cases(contract: AuditContract, repo_root: Path) -> CaseAudit:
    """Classify every frozen calendar anchor; never read a forward price into output."""
    if not contract.source_file.is_relative_to(repo_root.resolve()):
        raise ContractError("source path escapes repository root")
    anchors = _anchors(contract)
    input_refs, settlement_refs, source_bytes, rows_in_scope = _source_refs(contract, anchors)
    cases = []
    for index, anchor in enumerate(anchors):
        lookback_at = anchor.event_ms - contract.lookback_seconds * 1000
        inputs = {
            "lookback": _input_record(
                input_refs[index][0], lookback_at, contract.maximum_input_quote_age_seconds * 1000
            ),
            "anchor": _input_record(
                input_refs[index][1], anchor.event_ms, contract.maximum_input_quote_age_seconds * 1000
            ),
        }
        settlement_at = anchor.event_ms + contract.settlement_horizon_seconds * 1000
        settlement = _settlement_record(
            settlement_refs[index], settlement_at, contract.maximum_settlement_quote_delay_seconds * 1000
        )
        if not all(item["eligible"] for item in inputs.values()):
            status = "INPUT_MISSING"
        elif not settlement["eligible"]:
            status = "OUTCOME_MISSING"
        else:
            status = "MEASURABLE"
        cases.append(
            {
                "case_id": f"{contract.instrument}:{_iso(anchor.event_ms)}",
                "window": anchor.window,
                "anchor_utc": _iso(anchor.event_ms),
                "assumed_decision_at_utc": _iso(anchor.event_ms + contract.decision_delay_seconds * 1000),
                "inputs": inputs,
                "settlement_target_utc": _iso(settlement_at),
                "settlement": settlement,
                "status": status,
            }
        )
    return CaseAudit(contract, tuple(cases), source_bytes, rows_in_scope)


