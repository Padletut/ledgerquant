from copy import deepcopy
import asyncio

import httpx

from ledgerquant.capture.api import create_app
from ledgerquant.capture.storage import CaptureConflict
from tests.unit.test_capture_contracts import TICK


TOKEN = "t" * 40


class Store:
    def __init__(self):
        self.calls = 0
        self.conflict = False

    def ping(self):
        return None

    def append(self, batch, received_at):
        self.calls += 1
        if self.conflict:
            raise CaptureConflict()
        return len(batch.observations), 0


def body():
    return {
        "protocol_version": 1,
        "sent_at": "2026-10-08T10:00:01Z",
        "observations": [deepcopy(TICK)],
    }


def post(app, payload, token=None):
    async def send():
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://capture.test"
        ) as client:
            return await client.post("/v1/capture/batches", json=payload, headers=headers)

    return asyncio.run(send())


def test_authentication_and_commit_acknowledgement():
    store = Store()
    app = create_app(store, TOKEN)
    assert post(app, body()).status_code == 401
    response = post(app, body(), TOKEN)
    assert response.status_code == 200
    assert response.json() == {"committed": 1, "inserted": 1, "duplicates": 0}
    assert store.calls == 1


def test_invalid_payload_never_reaches_storage():
    store = Store()
    app = create_app(store, TOKEN)
    payload = body()
    payload["observations"][0]["ask"] = "1.00000"
    response = post(app, payload, TOKEN)
    assert response.status_code == 422
    assert store.calls == 0


def test_conflict_has_no_success_acknowledgement():
    store = Store()
    store.conflict = True
    response = post(create_app(store, TOKEN), body(), TOKEN)
    assert response.status_code == 409
