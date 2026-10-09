"""Resolve settlement quotes from a bounded part of the pinned CSV."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from .audit import _event_ms, _iso, _parse_source_row
from .contracts import ContractError, _utc


@dataclass(frozen=True)
class SettlementRequest:
    case_id: str
    target_utc: str


@dataclass(frozen=True)
class ResolvedSettlement:
    event_at_utc: str
    source_line: int
    midquote: str


def verify_source_sha256(source: Path, expected_sha256: str) -> None:
    """Hash the full file as bytes without interpreting holdout prices."""
    digest = sha256()
    try:
        with source.open("rb") as handle:
            for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ContractError(f"cannot read source: {exc}") from exc
    if digest.hexdigest() != expected_sha256:
        raise ContractError("source SHA-256 mismatch")


def resolve_settlements(
    source: Path,
    requests: list[SettlementRequest],
    end_exclusive_utc: str,
) -> dict[str, ResolvedSettlement]:
    """Read only through the declared window; use the first row at or after each target."""
    if not requests:
        return {}
    cutoff = _utc(end_exclusive_utc)
    targets = sorted((_event_ms(_utc(item.target_utc)), item.case_id) for item in requests)
    if len({case_id for _, case_id in targets}) != len(targets):
        raise ContractError("duplicate settlement case ID")
    if any(_utc(item.target_utc) >= cutoff for item in requests):
        raise ContractError("settlement target is outside the permitted window")
    first_day = min(item.target_utc[:10] for item in requests).encode("ascii")
    after_last_day = cutoff.date().isoformat().encode("ascii")
    found: dict[str, ResolvedSettlement] = {}
    target_index = 0
    cached_day = None
    day_ms = 0
    previous_ms = None
    try:
        with source.open("rb") as handle:
            for line_number, raw in enumerate(handle, 1):
                day = raw[:10]
                if day < first_day:
                    continue
                if day >= after_last_day:
                    break
                cached_day, day_ms, event_ms, midquote = _parse_source_row(
                    raw, line_number, cached_day, day_ms
                )
                if previous_ms is not None and event_ms < previous_ms:
                    raise ContractError(f"timestamp reversal at source line {line_number}")
                previous_ms = event_ms
                while target_index < len(targets) and targets[target_index][0] <= event_ms:
                    _, case_id = targets[target_index]
                    found[case_id] = ResolvedSettlement(
                        event_at_utc=_iso(event_ms),
                        source_line=line_number,
                        midquote=format(midquote, "f"),
                    )
                    target_index += 1
                if target_index == len(targets):
                    break
    except OSError as exc:
        raise ContractError(f"cannot read source: {exc}") from exc
    if len(found) != len(targets):
        raise ContractError("required settlement quote was not found in permitted window")
    return found
