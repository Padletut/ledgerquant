"""Versioned wire contract for the initial cTrader capture path."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CaptureObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: UUID
    feed_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    session_id: UUID
    sequence: int = Field(ge=1)
    source: Literal["ctrader"]
    broker: str = Field(min_length=1, max_length=120)
    environment: Literal["demo", "live"]
    account_id: str = Field(min_length=1, max_length=40)
    symbol: str = Field(min_length=1, max_length=64)
    kind: Literal["tick", "sentiment"]
    event_at: datetime | None = None
    observed_at: datetime
    bid: Decimal | None = None
    ask: Decimal | None = None
    buy_percentage: Decimal | None = None
    sell_percentage: Decimal | None = None
    sentiment_trigger: Literal["startup", "update"] | None = None
    cbot_version: str = Field(min_length=1, max_length=40)

    @field_validator("event_at", "observed_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("timestamps must carry a UTC offset")
        return value

    @model_validator(mode="after")
    def check_payload(self) -> "CaptureObservation":
        if self.kind == "tick":
            if (
                self.event_at is None
                or self.bid is None
                or self.ask is None
                or self.bid <= 0
                or self.ask < self.bid
                or self.buy_percentage is not None
                or self.sell_percentage is not None
                or self.sentiment_trigger is not None
            ):
                raise ValueError("invalid tick payload")
        elif (
            self.event_at is not None
            or self.bid is not None
            or self.ask is not None
            or self.buy_percentage is None
            or self.sell_percentage is None
            or self.sentiment_trigger is None
            or not 0 <= self.buy_percentage <= 100
            or not 0 <= self.sell_percentage <= 100
        ):
            raise ValueError("invalid sentiment payload")
        return self

    @property
    def quality_flag(self) -> str:
        if self.kind == "sentiment" and (
            self.buy_percentage == 0 or self.sell_percentage == 0
        ):
            return "ZERO_AMBIGUOUS"
        return "OBSERVED"


class CaptureBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal[1]
    sent_at: datetime
    observations: list[CaptureObservation] = Field(min_length=1, max_length=250)

    @field_validator("sent_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("sent_at must carry a UTC offset")
        return value

    @model_validator(mode="after")
    def unique_within_batch(self) -> "CaptureBatch":
        ids = [item.message_id for item in self.observations]
        sequences = [
            (item.feed_id, item.session_id, item.sequence)
            for item in self.observations
        ]
        if len(ids) != len(set(ids)) or len(sequences) != len(set(sequences)):
            raise ValueError("duplicate identity in batch")
        identities = {
            (
                item.feed_id,
                item.source,
                item.broker,
                item.environment,
                item.account_id,
                item.symbol,
            )
            for item in self.observations
        }
        if len(identities) != 1:
            raise ValueError("a batch must contain one feed and source identity")
        return self
