import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from ledgerquant.research.quote_quality import _ranks, evaluate_manifest, measure_windows


UTC = timezone.utc


def test_windows_do_not_read_future_quote_into_lookback():
    start = datetime(2020, 2, 11, 7, 30, tzinfo=UTC)
    anchor = start + timedelta(minutes=45)
    ticks = [(start + timedelta(seconds=second), 1.0) for second in range(1, 2700, 30)]
    ticks.extend((anchor + timedelta(seconds=second), 10.0) for second in range(0, 900, 30))

    case = measure_windows(ticks, start, [anchor])[0]

    assert case["status"] == "MEASURABLE"
    assert case["lookback_spread_iqr"] == 0.0
    assert case["forward_spread_p95"] == 10.0


def test_source_gap_retains_case_without_outcome():
    start = datetime(2020, 2, 11, 7, 30, tzinfo=UTC)
    anchor = start + timedelta(minutes=45)
    ticks = [(start + timedelta(seconds=1), 1.0)]

    case = measure_windows(ticks, start, [anchor])[0]

    assert case["status"] == "INSUFFICIENT_SOURCE"
    assert case["lookback_spread_iqr"] is None
    assert case["forward_spread_p95"] is None


def test_numerical_noise_does_not_break_spread_rank_ties():
    assert _ranks([0.03, 0.03000000000000002, 0.04]) == [0.5, 0.5, 2.0]


def test_manifest_hash_is_required(tmp_path):
    day = "2020-02-11"
    csv_path = tmp_path / "sample.ticks.csv"
    csv_path.write_text("ordinal,event_time_utc,bid,ask\n1,2020-02-11T07:30:00Z,1,2\n")
    manifest = {
        "source_type": "broker_historical_tick_backfill",
        "broker_name": "IC Markets EU Ltd",
        "account_number": 123456,
        "account_environment": "live",
        "broker_symbol": "XAUUSD",
        "data_mode": "ctrader_cli_server_ticks",
        "requested_start_utc": "2020-02-11T07:30:00Z",
        "requested_end_exclusive_utc": "2020-02-11T16:15:00Z",
        "row_count": 1,
        "data_file": csv_path.name,
        "data_bytes": csv_path.stat().st_size,
        "data_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
    }
    path = tmp_path / f"xauusd_{day}-quote-dev-v1.manifest.json"
    path.write_text(json.dumps(manifest))
    csv_path.write_text(csv_path.read_text().replace(",1,2", ",1,3"))

    with pytest.raises(ValueError, match="hash"):
        evaluate_manifest(path, day, 123456)

    with pytest.raises(ValueError, match="account"):
        evaluate_manifest(path, day, 654321)
