"""Source-presence checks used before freezing a new validation window."""

from datetime import date
from hashlib import sha256
from pathlib import Path

import pytest

from ledgerquant.research.contracts import ContractError
from ledgerquant.research.source_coverage import scan_source_window


def test_coverage_reports_quotes_and_dates_without_research_outcomes(tmp_path: Path):
    source = tmp_path / "ticks.csv"
    source.write_bytes(
        b"2020-12-31,23:59:59.000,1.00000,1.00000\n"
        b"2021-01-04,08:00:00.000,1.10000,1.10000\n"
        b"2021-01-04,08:00:00.000,1.10000,1.10001\n"
        b"2021-01-06,12:00:00.000,1.20000,1.20002\n"
    )
    result = scan_source_window(
        source,
        sha256(source.read_bytes()).hexdigest(),
        date(2021, 1, 4),
        date(2021, 1, 7),
    )

    assert result["rows_in_scope"] == 3
    assert result["observed_utc_dates"] == 2
    assert result["weekday_dates_without_rows"] == ["2021-01-05"]
    assert result["identical_bid_ask_rows"] == 1
    assert result["equal_timestamp_rows"] == 1
    assert result["monthly_presence"] == {"2021-01": {"rows": 3, "observed_utc_dates": 2}}
    assert result["contains_predictions_or_outcomes"] is False
    assert "accuracy" not in result


def test_coverage_rejects_wrong_source_hash_and_reversed_timestamps(tmp_path: Path):
    source = tmp_path / "ticks.csv"
    source.write_bytes(
        b"2021-01-04,08:00:01.000,1.10000,1.10001\n"
        b"2021-01-04,08:00:00.000,1.10000,1.10001\n"
    )
    with pytest.raises(ContractError, match="timestamp reversal"):
        scan_source_window(source, sha256(source.read_bytes()).hexdigest(), date(2021, 1, 1), date(2021, 2, 1))

    source.write_bytes(b"2021-01-04,08:00:00.000,1.10000,1.10001\n")
    with pytest.raises(ContractError, match="source SHA-256 mismatch"):
        scan_source_window(source, "0" * 64, date(2021, 1, 1), date(2021, 2, 1))
