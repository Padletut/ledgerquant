"""The runner accepts only explicit, versioned model bindings."""

from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import Field

from ledgerquant.research.types import Record


class ModelProfile(Record):
    provider: str = Field(min_length=1, max_length=40)
    endpoint: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=120)
    max_output_tokens: int = Field(ge=256, le=8192)
    max_request_bytes: int = Field(ge=4096, le=200000)
    timeout_seconds: int = Field(ge=5, le=300)
    max_steps_per_agent: int = Field(ge=1, le=8)
    reasoning_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    input_usd_per_million: float = Field(ge=0, allow_inf_nan=False)
    cache_write_usd_per_million: float = Field(default=0, ge=0, allow_inf_nan=False)
    output_usd_per_million: float = Field(ge=0, allow_inf_nan=False)
    max_run_usd: float = Field(gt=0, allow_inf_nan=False)
    price_basis: str = Field(min_length=1, max_length=500)
    knowledge_exposure: str = Field(min_length=1, max_length=500)


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class Generation:
    status: str
    raw: dict
    continuation: list[dict]
    calls: tuple[ToolCall, ...] = ()
    input_tokens: int | None = None
    output_tokens: int | None = None


class Provider(Protocol):
    profile: ModelProfile

    def prepare(self, instructions: str, conversation: list[dict], tools: list[dict]) -> dict: ...
    def invoke(self, request: dict) -> Generation: ...
    def user_message(self, value: str) -> dict: ...
    def tool_result(self, call_id: str, result: str) -> dict: ...
