from copy import deepcopy

import pytest
from pydantic import ValidationError

from ledgerquant.capture.contracts import CaptureBatch, CaptureObservation


TICK = {
    "message_id": "2c612b5c-cf86-40ec-8c6f-3e1e09e7a209",
    "feed_id": "icm_live_eurusd",
    "session_id": "4ac12ac7-19df-434d-a1b8-6abfda9e552a",
    "sequence": 1,
    "source": "ctrader",
    "broker": "IC Markets EU",
    "environment": "live",
    "account_id": "12345",
    "symbol": "EURUSD",
    "kind": "tick",
    "event_at": "2026-10-08T10:00:00.123Z",
    "observed_at": "2026-10-08T10:00:00.130Z",
    "bid": "1.12340",
    "ask": "1.12352",
    "cbot_version": "capture-0.1.0",
}


def test_tick_and_sentiment_are_distinct_typed_observations():
    tick = CaptureObservation.model_validate(TICK)
    assert tick.quality_flag == "OBSERVED"

    sentiment = deepcopy(TICK)
    sentiment.update(
        kind="sentiment",
        event_at=None,
        bid=None,
        ask=None,
        buy_percentage="0",
        sell_percentage="0",
        sentiment_trigger="startup",
    )
    result = CaptureObservation.model_validate(sentiment)
    assert result.event_at is None
    assert result.quality_flag == "ZERO_AMBIGUOUS"


@pytest.mark.parametrize(
    "field,value",
    [
        ("event_at", None),
        ("bid", "1.20000"),
        ("observed_at", "2026-10-08T10:00:00"),
        ("feed_id", "../other-feed"),
    ],
)
def test_invalid_tick_is_rejected(field, value):
    payload = deepcopy(TICK)
    payload[field] = value
    with pytest.raises(ValidationError):
        CaptureObservation.model_validate(payload)


def test_batch_rejects_reused_identity():
    with pytest.raises(ValidationError):
        CaptureBatch.model_validate(
            {
                "protocol_version": 1,
                "sent_at": "2026-10-08T10:00:01Z",
                "observations": [TICK, TICK],
            }
        )


def test_batch_rejects_mixed_source_identity():
    other = deepcopy(TICK)
    other["message_id"] = "6c6dfe0b-09f0-4dd7-8c9f-0bcb69b5ae25"
    other["sequence"] = 2
    other["account_id"] = "other-account"
    with pytest.raises(ValidationError):
        CaptureBatch.model_validate(
            {
                "protocol_version": 1,
                "sent_at": "2026-10-08T10:00:01Z",
                "observations": [TICK, other],
            }
        )
