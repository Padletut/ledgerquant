import json

import anthropic
import httpx2
import pytest

from ledgerquant.integrations.model_providers.anthropic import ENDPOINT, AnthropicMessages, decode
from ledgerquant.models.generation import ModelProfile
from ledgerquant.pipeline.analyst import TOOL

USAGE = {"input_tokens": 1200, "output_tokens": 300}


def profile(**overrides):
    return ModelProfile(**({"provider": "anthropic", "endpoint": ENDPOINT, "model": "claude-test",
        "max_output_tokens": 4096, "max_request_bytes": 40000, "timeout_seconds": 10, "max_steps_per_agent": 1,
        "input_usd_per_million": 5, "output_usd_per_million": 25, "max_run_usd": 1, "price_basis": "test fixture",
        "knowledge_exposure": "unknown"} | overrides))


class FakeMessages:
    def __init__(self, result):
        self.result, self.requests = result, []

    def create(self, **request):
        self.requests.append(request)
        if isinstance(result := self.result, Exception):
            raise result
        return anthropic.types.Message.model_validate(result)


class FakeClient:
    def __init__(self, result):
        self.messages = FakeMessages(result)


def message(content, stop_reason="tool_use"):
    return {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-test", "content": content,
            "stop_reason": stop_reason, "stop_sequence": None, "usage": USAGE}


def test_request_uses_adaptive_thinking_one_tool_call_and_no_retries():
    p = AnthropicMessages(profile(), "", client=FakeClient(None))
    request = p.prepare("instructions", [p.user_message("task")], [TOOL])
    assert request["thinking"] == {"type": "adaptive"} and request["output_config"] == {"effort": "medium"}
    assert request["tool_choice"] == {"type": "auto", "disable_parallel_tool_use": True}
    assert request["tools"][0]["input_schema"] == TOOL["parameters"]
    assert request["system"].startswith("instructions") and "exactly once" in request["system"]
    real = AnthropicMessages(profile(), "private-test-key")
    assert real._client.max_retries == 0
    with pytest.raises(ValueError):
        AnthropicMessages(profile(), "bad key")
    with pytest.raises(ValueError):
        AnthropicMessages(profile(provider="openai"), "k")


def test_one_tool_call_is_completed_with_usage():
    answer = {"views": {}, "action": "NO_SIGNAL"}
    content = [{"type": "thinking", "thinking": "t", "signature": "s"},
               {"type": "tool_use", "id": "toolu_1", "name": "submit_analysis", "input": answer}]
    p = AnthropicMessages(profile(), "", client=FakeClient(message(content)))
    generation = p.invoke(p.prepare("i", [p.user_message("x")], [TOOL]))
    assert generation.status == "COMPLETED" and generation.calls[0].name == "submit_analysis"
    assert json.loads(generation.calls[0].arguments) == answer
    assert (generation.input_tokens, generation.output_tokens) == (1200, 300)


def test_text_refusal_truncation_and_errors_are_not_parsed():
    assert decode(message([{"type": "text", "text": "LONG"}], "end_turn")).status == "NO_TOOL_CALL"
    assert decode(message([], "refusal")).status == "REFUSED"
    assert decode(message([], "max_tokens")).status == "INCOMPLETE"
    two = [{"type": "tool_use", "id": f"t{i}", "name": "submit_analysis", "input": {}} for i in range(2)]
    assert decode(message(two)).status == "MALFORMED_RESPONSE"
    request = httpx2.Request("POST", ENDPOINT)
    error = anthropic.RateLimitError("slow down", response=httpx2.Response(429, request=request, text="{}"), body=None)
    p = AnthropicMessages(profile(), "", client=FakeClient(error))
    generation = p.invoke({})
    assert generation.status == "HTTP_ERROR" and generation.raw["http_status"] == 429
    p = AnthropicMessages(profile(), "", client=FakeClient(anthropic.APITimeoutError(request=request)))
    assert p.invoke({}).status == "DISPATCH_UNKNOWN"
