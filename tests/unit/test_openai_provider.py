import json

import httpx
import pytest

from ledgerquant.decision.shadow import SHADOW_TOOL
from ledgerquant.models.generation import ModelProfile
from ledgerquant.integrations.model_providers.openai import OpenAIResponses


def profile(**overrides):
    return ModelProfile(**({"provider": "openai", "endpoint": "https://api.openai.com/v1/responses",
        "model": "configured-test-model", "max_output_tokens": 512, "max_request_bytes": 40000,
        "timeout_seconds": 10, "max_steps_per_agent": 6, "input_usd_per_million": 1,
        "output_usd_per_million": 5, "max_run_usd": 1, "price_basis": "test fixture",
        "knowledge_exposure": "unknown training exposure"} | overrides))


def provider(handler):
    return OpenAIResponses(profile(), "private-test-key", transport=httpx.MockTransport(handler))


def test_exact_stateless_request_and_strict_schema():
    p = provider(lambda request: httpx.Response(200))
    request = p.prepare("instructions", [p.user_message("task")], [SHADOW_TOOL])
    assert request["store"] is False
    assert request["parallel_tool_calls"] is False
    assert "private-test-key" not in json.dumps(request)
    for tool in request["tools"]:
        assert tool["strict"] is True
        schema = tool["parameters"]
        assert set(schema["required"]) == set(schema["properties"])
        for child in schema.get("$defs", {}).values():
            if child.get("type") == "object":
                assert child["additionalProperties"] is False
                assert set(child["required"]) == set(child["properties"])


def test_raw_response_identity_and_usage_preserved():
    body = {"status": "completed", "model": "returned-version", "id": "resp_test",
            "output": [{"type": "function_call", "call_id": "call_1", "name": "submit_shadow_decision", "arguments": "{}"}],
            "usage": {"input_tokens": 100, "output_tokens": 12}}
    p = provider(lambda request: httpx.Response(200, json=body, headers={"x-request-id": "req_test"}))
    result = p.invoke(p.prepare("instructions", [], [SHADOW_TOOL]))
    assert result.calls[0].name == "submit_shadow_decision"
    assert result.input_tokens == 100
    assert json.loads(result.raw["body"])["model"] == "returned-version"
    assert result.raw["request_id"] == "req_test"
    assert p.tool_result("call_1", "{}")["call_id"] == "call_1"


@pytest.mark.parametrize("status,body,expected", [(429, '{"error":{"message":"rate limit"}}', "HTTP_ERROR"),
    (200, "not JSON", "MALFORMED_RESPONSE"), (200, '{"status":"incomplete","output":[]}', "INCOMPLETE")])
def test_failures_retain_wire_content_and_never_retry(status, body, expected):
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(status, text=body)
    result = provider(handle).invoke({"model": "configured-test-model"})
    assert result.status == expected
    assert result.raw["body"] == body
    assert len(calls) == 1


def test_timeout_usage_unknown_and_endpoint_restricted():
    def timeout(request):
        raise httpx.ReadTimeout("contains secret; must not log", request=request)
    result = provider(timeout).invoke({})
    assert result.status == "DISPATCH_UNKNOWN"
    assert result.input_tokens is None
    assert "secret" not in json.dumps(result.raw)
    with pytest.raises(ValueError):
        OpenAIResponses(profile(endpoint="http://example.org"), "private-test-key")
