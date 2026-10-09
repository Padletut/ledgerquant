"""Explicit OpenAI Responses binding; no retries, hosted tools or fallback."""

from copy import deepcopy
import json

import httpx

from ledgerquant.research.types import canonical
from ledgerquant.models.generation import Generation, ModelProfile, ToolCall


def strict_schema(schema):
    """All catalog fields are required on the wire, including domain defaults."""
    result = deepcopy(schema)
    def visit(node):
        if isinstance(node, dict):
            node.pop("default", None)
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}))
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)
    visit(result)
    return result


class OpenAIResponses:
    def __init__(self, profile: ModelProfile, api_key: str, *, transport=None):
        if profile.provider != "openai" or profile.endpoint != "https://api.openai.com/v1/responses":
            raise ValueError("this adapter requires the explicit OpenAI Responses endpoint")
        if not api_key.strip() or any(char.isspace() for char in api_key.strip()):
            raise ValueError("OpenAI credential is empty or malformed")
        self.profile = profile
        self._key, self._transport = api_key.strip(), transport

    def prepare(self, instructions, conversation, tools):
        request = {"model": self.profile.model, "instructions": instructions, "input": conversation,
                   "tools": [{"type": "function", "name": tool["name"], "description": tool["description"],
                              "parameters": strict_schema(tool["parameters"]), "strict": True} for tool in tools],
                   "tool_choice": "required", "parallel_tool_calls": False, "store": False,
                   "reasoning": {"effort": self.profile.reasoning_effort}, "service_tier": "default",
                   "include": ["reasoning.encrypted_content"], "max_output_tokens": self.profile.max_output_tokens}
        if len(canonical(request).encode()) > self.profile.max_request_bytes:
            raise ValueError("REQUEST_BUDGET_EXCEEDED")
        return request

    @staticmethod
    def user_message(value):
        return {"role": "user", "content": value}

    @staticmethod
    def tool_result(call_id, result):
        return {"type": "function_call_output", "call_id": call_id, "output": result}

    def invoke(self, request):
        raw = {}
        try:
            with httpx.Client(timeout=self.profile.timeout_seconds, transport=self._transport,
                              trust_env=False, follow_redirects=False) as client:
                with client.stream("POST", self.profile.endpoint, content=canonical(request).encode(),
                                   headers={"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}) as response:
                    raw = {"http_status": response.status_code, "request_id": response.headers.get("x-request-id")}
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        content.extend(chunk)
                        if len(content) > 2_000_000:
                            raw["body_prefix"] = content[:2_000_000].decode(errors="replace")
                            return Generation("RESPONSE_TOO_LARGE", raw, [])
                    raw["body"] = content.decode(errors="replace")
                    if response.status_code != 200:
                        return Generation("HTTP_ERROR", raw, [])
        except httpx.HTTPError as exc:
            raw["transport_error"] = type(exc).__name__
            return Generation("DISPATCH_UNKNOWN", raw, [])
        return decode(raw)


def decode(raw):
    try:
        body = json.loads(raw["body"])
        output = body.get("output", [])
        usage = body.get("usage") or {}
        incoming, outgoing = usage.get("input_tokens"), usage.get("output_tokens")
        if any(type(n) is not int or n < 0 for n in (incoming, outgoing) if n is not None):
            raise ValueError("invalid usage")
        if body.get("status") != "completed":
            return Generation("INCOMPLETE", raw, [], (), incoming, outgoing)
        if any(c.get("type") == "refusal" for item in output for c in item.get("content", [])):
            return Generation("REFUSED", raw, [], (), incoming, outgoing)
        calls = tuple(ToolCall(item["call_id"], item["name"], item["arguments"])
                      for item in output if item["type"] == "function_call")
        if not calls or len(calls) != 1 or not all(isinstance(x, str) for call in calls for x in (call.id, call.name, call.arguments)):
            raise ValueError("exactly one well-formed tool call required")
        return Generation("COMPLETED", raw, output, calls, incoming, outgoing)
    except (ValueError, TypeError, KeyError, AttributeError):
        return Generation("MALFORMED_RESPONSE", raw, [])
