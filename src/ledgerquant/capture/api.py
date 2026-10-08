"""Small authenticated ingest surface; no execution or control operations."""

import hmac
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from ledgerquant.capture.contracts import CaptureBatch
from ledgerquant.capture.storage import CaptureConflict, CaptureStore


MAX_BODY_BYTES = 1_048_576


def create_app(store: CaptureStore, collector_token: str) -> FastAPI:
    app = FastAPI(
        title="LedgerQuant capture ingest",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.get("/healthz")
    def health() -> dict[str, str]:
        try:
            store.ping()
        except SQLAlchemyError as error:
            raise HTTPException(status_code=503, detail="database unavailable") from error
        return {"status": "ready"}

    @app.post("/v1/capture/batches")
    async def capture(request: Request) -> dict[str, int]:
        authorization = request.headers.get("authorization", "")
        expected = f"Bearer {collector_token}"
        if not hmac.compare_digest(authorization, expected):
            raise HTTPException(status_code=401, detail="unauthorized")
        content_length = request.headers.get("content-length")
        if content_length is not None and (
            not content_length.isdecimal() or int(content_length) > MAX_BODY_BYTES
        ):
            raise HTTPException(status_code=413, detail="batch too large")
        body = await request.body()
        if len(body) > MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="batch too large")
        received_at = datetime.now(timezone.utc)
        try:
            batch = CaptureBatch.model_validate_json(body)
        except ValidationError as error:
            raise HTTPException(status_code=422, detail="invalid capture batch") from error
        try:
            inserted, duplicates = store.append(batch, received_at)
        except CaptureConflict as error:
            raise HTTPException(status_code=409, detail="observation identity conflict") from error
        except SQLAlchemyError as error:
            raise HTTPException(status_code=503, detail="database unavailable") from error
        return {"committed": len(batch.observations), "inserted": inserted, "duplicates": duplicates}

    return app
