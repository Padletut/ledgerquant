from ledgerquant.replay.risk import check_entry

TIMES = {"hours_to_weekend_close": 5.5}


def test_entry_horizon_is_checked_only_against_the_chosen_limit():
    assert check_entry({"expected_horizon_hours": 5}, {"close_before_weekend": True}, TIMES) is None
    assert check_entry({"expected_horizon_hours": 6}, {"close_before_weekend": True}, TIMES) == \
        "HORIZON_EXCEEDS_WEEKEND_CLOSE"
    assert check_entry({"expected_horizon_hours": 240}, {"close_before_weekend": False}, TIMES) is None
