"""Read the frozen contract supported by the first EURUSD case audit."""

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re


class ContractError(ValueError):
    """A frozen contract or its source cannot be used safely."""


@dataclass(frozen=True)
class Window:
    name: str
    start: datetime
    end: datetime
    minimum_eligible_anchors: int


@dataclass(frozen=True)
class AuditContract:
    hypothesis_id: str
    contract_sha256: str
    freeze_sha256: str
    source_file: Path
    source_sha256: str
    source_id: str
    instrument: str
    windows: tuple[Window, ...]
    iso_weekdays: tuple[int, ...]
    hours_utc: tuple[int, ...]
    decision_delay_seconds: int
    lookback_seconds: int
    settlement_horizon_seconds: int
    maximum_input_quote_age_seconds: int
    maximum_settlement_quote_delay_seconds: int
    maximum_unmeasurable_fraction: float


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _utc(value: str) -> datetime:
    _require(isinstance(value, str) and value.endswith("Z"), "UTC timestamp required")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError("invalid UTC timestamp") from exc
    _require(result.tzinfo == timezone.utc, "UTC timestamp required")
    return result


def _window(name: str, value: dict) -> Window:
    start = _utc(value["start_inclusive_utc"])
    end = _utc(value["end_exclusive_utc"])
    minimum = value["minimum_eligible_anchors"]
    _require(start < end, "window start must precede end")
    _require(type(minimum) is int and minimum > 0, "invalid minimum support")
    _require(
        start.time() == datetime.min.time() and end.time() == datetime.min.time(),
        "windows must start at UTC midnight",
    )
    return Window(name, start, end, minimum)


def _inside(root: Path, relative: str) -> Path:
    _require(isinstance(relative, str), "relative path required")
    candidate = (root / relative).resolve()
    _require(candidate.is_relative_to(root), "path escapes repository root")
    return candidate


def load_frozen_contract(repo_root: Path, freeze_path: Path) -> AuditContract:
    """Verify the freeze hash and reject semantics this audit cannot enforce."""
    root = repo_root.resolve()
    freeze_file = freeze_path.resolve()
    _require(freeze_file.is_relative_to(root), "freeze path escapes repository root")
    try:
        freeze_bytes = freeze_file.read_bytes()
        freeze = json.loads(freeze_bytes)
        _require(freeze["schema_version"] == 1, "unsupported freeze schema")
        _require(freeze["event_type"] == "CONTRACT_FROZEN", "contract is not frozen")
        contract_file = _inside(root, freeze["contract_path"])
        contract_bytes = contract_file.read_bytes()
        digest = sha256(contract_bytes).hexdigest()
        _require(digest == freeze["contract_sha256"], "contract SHA-256 mismatch")
        contract = json.loads(contract_bytes)
        _require(contract["schema_version"] == 1, "unsupported contract schema")
        _require(contract["hypothesis_id"] == freeze["hypothesis_id"], "hypothesis ID mismatch")

        decision = contract["decision_contract"]
        feature = contract["feature_contract"]
        payoff = contract["payoff_contract"]
        policy = contract["data_sufficiency_policy"]
        event = decision["candidate_event_rule"]
        _require(contract["evidence_mode"] == "retrospective_historical_simulation", "unsupported evidence mode")
        _require(contract["economic_claim"] == "none_predictive_diagnostic_only", "economic claim is unsupported")
        _require(decision["orders_allowed"] is False, "orders are unsupported")
        _require(decision["candidate_rule"] == "prior_hour_midquote_momentum_sign", "unsupported candidate rule")
        _require(feature["quote_field"] == "midquote_decimal", "unsupported quote field")
        _require(
            feature["quote_calculation"] == "(bid + ask) / 2 with decimal arithmetic",
            "unsupported quote calculation",
        )
        _require(feature["input_quote_selection"] == "last_at_or_before", "unsupported input selection")
        _require(feature["news_or_sentiment"] == "none", "news input is unsupported")
        _require(payoff["target"] == "positive_settlement_minus_anchor_midquote", "unsupported target")
        _require(payoff["settlement_quote_selection"] == "first_at_or_after", "unsupported settlement selection")
        _require(payoff["path_dependent"] is False, "path-dependent payoff is unsupported")
        _require(payoff["promotion_eligible"] is False, "promotion is unsupported")
        _require(contract["cost_contract"]["net_payoff"] == "not_defined", "net payoff is unsupported")
        _require(policy["visibility_mode"] == "retrospective_assumed_server_quote_visibility", "unsupported visibility mode")
        _require(policy["actual_historical_available_at"] is None, "historical availability cannot be asserted")
        _require(policy["quote_order"] == "source_csv_order", "unsupported source order")
        _require(
            policy["source_view_failure_reasons"] == [
                "SOURCE_HASH_MISMATCH",
                "MALFORMED_ROW",
                "NONPOSITIVE_QUOTE",
                "CROSSED_QUOTE",
                "TIMESTAMP_REVERSAL",
            ],
            "unsupported source validation policy",
        )
        _require(policy["case_status_precedence"] == ["INPUT_MISSING", "OUTCOME_MISSING", "MEASURABLE"], "unsupported case precedence")
        _require(policy["score_only_status"] == "MEASURABLE", "unsupported score status")
        _require(policy["replacement_anchors_allowed"] is False, "replacement anchors are unsupported")
        _require(policy["tolerance_changes_allowed"] is False, "tolerance changes are unsupported")
        _require(event["generate_before_price_access"] is True, "anchors must precede price access")
        _require(event["include_holidays"] is True, "holiday filtering is unsupported")

        weekdays = event["iso_weekdays"]
        hours = event["hours_utc"]
        _require(bool(weekdays) and weekdays == sorted(set(weekdays)) and all(type(v) is int and 1 <= v <= 7 for v in weekdays), "invalid weekdays")
        _require(bool(hours) and hours == sorted(set(hours)) and all(type(v) is int and 0 <= v <= 23 for v in hours), "invalid UTC hours")
        source_sha = feature["source_sha256"]
        _require(bool(re.fullmatch(r"[0-9a-f]{64}", source_sha)), "invalid source SHA-256")
        windows = (_window("development", contract["development_window"]),)
        validation = contract["validation_windows"]
        _require(len(validation) == 1, "this audit supports one validation window")
        windows += (_window("validation", validation[0]),)
        _require(windows[0].end <= windows[1].start, "development and validation overlap")
        for field, value in (
            ("decision delay", decision["decision_delay_seconds"]),
            ("lookback", feature["lookback_seconds"]),
            ("settlement horizon", payoff["settlement_horizon_seconds"]),
            ("input age", policy["maximum_input_quote_age_seconds"]),
            ("settlement delay", policy["maximum_settlement_quote_delay_seconds"]),
        ):
            _require(type(value) is int and value > 0, f"invalid {field}")
        missing_limit = payoff["success_gate"]["maximum_unmeasurable_fraction_per_window"]
        _require(type(missing_limit) in (int, float) and 0 <= missing_limit < 1, "invalid missingness gate")
        source_file = _inside(root, feature["source_file"])
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ContractError(f"invalid frozen contract: {exc}") from exc

    return AuditContract(
        hypothesis_id=contract["hypothesis_id"],
        contract_sha256=digest,
        freeze_sha256=sha256(freeze_bytes).hexdigest(),
        source_file=source_file,
        source_sha256=source_sha,
        source_id=feature["source_id"],
        instrument=decision["instrument"],
        windows=windows,
        iso_weekdays=tuple(weekdays),
        hours_utc=tuple(hours),
        decision_delay_seconds=decision["decision_delay_seconds"],
        lookback_seconds=feature["lookback_seconds"],
        settlement_horizon_seconds=payoff["settlement_horizon_seconds"],
        maximum_input_quote_age_seconds=policy["maximum_input_quote_age_seconds"],
        maximum_settlement_quote_delay_seconds=policy["maximum_settlement_quote_delay_seconds"],
        maximum_unmeasurable_fraction=float(missing_limit),
    )
