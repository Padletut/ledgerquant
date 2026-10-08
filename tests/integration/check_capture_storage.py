"""Run against a disposable migrated PostgreSQL database."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from ledgerquant.capture.contracts import CaptureBatch
from ledgerquant.capture.settings import database_url_from_environment
from ledgerquant.capture.storage import CaptureConflict, create_store, observations


def main() -> None:
    now = datetime.now(timezone.utc)
    session_id = str(uuid4())
    feed_id = "integration_" + uuid4().hex
    identity = {
        "feed_id": feed_id,
        "session_id": session_id,
        "source": "ctrader",
        "broker": "integration-test",
        "environment": "demo",
        "account_id": "integration-test",
        "symbol": "EURUSD",
        "cbot_version": "capture-integration-test",
        "observed_at": now.isoformat(),
    }
    tick = {
        **identity,
        "message_id": str(uuid4()),
        "sequence": 1,
        "kind": "tick",
        "event_at": now.isoformat(),
        "bid": "1.10000",
        "ask": "1.10010",
    }
    sentiment = {
        **identity,
        "message_id": str(uuid4()),
        "sequence": 2,
        "kind": "sentiment",
        "buy_percentage": "0",
        "sell_percentage": "0",
        "sentiment_trigger": "startup",
    }
    batch_data = {
        "protocol_version": 1,
        "sent_at": now.isoformat(),
        "observations": [tick, sentiment],
    }
    batch = CaptureBatch.model_validate(batch_data)
    store = create_store(database_url_from_environment())
    inserted = store.append(batch, now)
    assert inserted == (2, 0), inserted
    duplicate = store.append(batch, now)
    assert duplicate == (0, 2), duplicate

    changed = {**tick, "bid": "1.10001"}
    conflicting = CaptureBatch.model_validate({**batch_data, "observations": [changed]})
    try:
        store.append(conflicting, now)
    except CaptureConflict:
        pass
    else:
        raise AssertionError("changed duplicate was accepted")

    reused_sequence = {**tick, "message_id": str(uuid4())}
    conflicting = CaptureBatch.model_validate({**batch_data, "observations": [reused_sequence]})
    try:
        store.append(conflicting, now)
    except CaptureConflict:
        pass
    else:
        raise AssertionError("source sequence was reused with a new message ID")

    other_identity = {**tick, "message_id": str(uuid4()), "account_id": "other-account"}
    conflicting = CaptureBatch.model_validate({**batch_data, "observations": [other_identity]})
    try:
        store.append(conflicting, now)
    except CaptureConflict:
        pass
    else:
        raise AssertionError("feed identity changed")

    with store.engine.connect() as connection:
        rows = connection.execute(
            select(observations).where(observations.c.feed_id == feed_id).order_by(observations.c.sequence)
        ).mappings().all()
    assert len(rows) == 2
    assert rows[0]["bid"] is not None and rows[0]["event_at"] is not None
    assert rows[1]["event_at"] is None
    assert rows[1]["quality_flag"] == "ZERO_AMBIGUOUS"
    assert all(row["received_at"] <= row["ingested_at"] for row in rows)

    try:
        with store.engine.begin() as connection:
            connection.execute(
                text("UPDATE market.capture_observations SET symbol = 'OTHER' WHERE feed_id = :feed"),
                {"feed": feed_id},
            )
    except DBAPIError:
        pass
    else:
        raise AssertionError("append-only update was accepted")

    print("capture storage integration passed")


if __name__ == "__main__":
    main()
