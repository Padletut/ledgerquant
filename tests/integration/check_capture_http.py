"""Exercise the live HTTP boundary against a disposable capture database."""

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def send(url: str, payload: dict, token: str | None) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
    )
    try:
        response = urllib.request.urlopen(request, timeout=10)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, json.loads(response.read())


def main() -> None:
    url = os.environ["CAPTURE_TEST_URL"]
    token = Path(os.environ["CAPTURE_TEST_TOKEN_FILE"]).read_text(encoding="utf-8").strip()
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "protocol_version": 1,
        "sent_at": now,
        "observations": [
            {
                "message_id": str(uuid4()),
                "feed_id": "integration_" + uuid4().hex,
                "session_id": str(uuid4()),
                "sequence": 1,
                "source": "ctrader",
                "broker": "integration-test",
                "environment": "demo",
                "account_id": "integration-test",
                "symbol": "EURUSD",
                "kind": "sentiment",
                "observed_at": now,
                "buy_percentage": "52.5",
                "sell_percentage": "47.5",
                "sentiment_trigger": "startup",
                "cbot_version": "capture-integration-test",
            }
        ],
    }
    assert send(url, payload, None)[0] == 401
    assert send(url, payload, token) == (
        200,
        {"committed": 1, "inserted": 1, "duplicates": 0},
    )
    assert send(url, payload, token) == (
        200,
        {"committed": 1, "inserted": 0, "duplicates": 1},
    )
    payload["observations"][0]["buy_percentage"] = "55.0"
    assert send(url, payload, token)[0] == 409
    print("capture HTTP integration passed")


if __name__ == "__main__":
    main()
