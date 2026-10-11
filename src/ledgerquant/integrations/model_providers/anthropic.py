"""Explicit Anthropic Messages binding; no retries, server tools or fallback.

Adaptive thinking cannot be combined with a forced tool choice, so the request
uses `tool_choice: auto` with parallel calls disabled and a fixed note asking for
exactly one tool call. An answer without that call is `NO_TOOL_CALL`, never
parsed from text.
"""

import json

import anthropic

from ledgerquant.models.generation import Generation, ModelProfile, ToolCall
from ledgerquant.records import canonical

ENDPOINT = "https://api.anthropic.com/v1/messages"
TOOL_NOTE = "\n\nAnswer only by calling the provided tool exactly once. Do not answer in text."


class AnthropicMessages:
    def __init__(self, profile: ModelProfile, api_key: str, *, client=None):
        if profile.provider != "anthropic" or profile.endpoint != ENDPOINT:
            raise ValueError("this adapter requires the explicit Anthropic Messages endpoint")
        if client is None and (not api_key.strip() or any(char.isspace() for char in api_key.strip())):
            raise ValueError("Anthropic credential is empty or malformed")
        self.profile = profile
        self._client = client or anthropic.Anthropic(api_key=api_key.strip(), max_retries=0,
                                                     timeout=float(profile.timeout_seconds))

    def prepare(self, instructions, conversation, tools):
        request = {"model": self.profile.model, "max_tokens": self.profile.max_output_tokens,
                   "system": instructions + TOOL_NOTE, "messages": conversation,
                   "tools": [{"name": tool["name"], "description": tool["description"],
                              "input_schema": tool["parameters"]} for tool in tools],
                   "tool_choice": {"type": "auto", "disable_parallel_tool_use": True},
                   "thinking": {"type": "adaptive"},
                   "output_config": {"effort": self.profile.reasoning_effort}}
        if len(canonical(request).encode()) > self.profile.max_request_bytes:
            raise ValueError("REQUEST_BUDGET_EXCEEDED")
        return request

    @staticmethod
    def user_message(value):
        return {"role": "user", "content": value}

    @staticmethod
    def tool_result(call_id, result):
        return {"role": "user", "content": [{"type": "tool_result", "tool_use_id": call_id, "content": result}]}

    def invoke(self, request):
        try:
            response = self._client.messages.create(**request)
        except anthropic.APIStatusError as exc:
            return Generation("HTTP_ERROR", {"http_status": exc.status_code, "request_id": exc.request_id,
                                             "body": exc.response.text[:20000]}, [])
        except (anthropic.APITimeoutError, anthropic.APIConnectionError) as exc:
            return Generation("DISPATCH_UNKNOWN", {"transport_error": type(exc).__name__}, [])
        return decode(response.model_dump(mode="json"))


def decode(body: dict) -> Generation:
    raw = {"body": body, "request_id": body.get("_request_id")}
    try:
        usage = body.get("usage") or {}
        incoming = sum(usage.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens",
                                                   "cache_read_input_tokens"))
        outgoing = usage.get("output_tokens")
        if type(outgoing) is not int or outgoing < 0:
            raise ValueError("invalid usage")
        content, stop = body.get("content") or [], body.get("stop_reason")
        if stop == "refusal":
            return Generation("REFUSED", raw, [], (), incoming, outgoing)
        if stop == "max_tokens":
            return Generation("INCOMPLETE", raw, [], (), incoming, outgoing)
        calls = tuple(ToolCall(block["id"], block["name"], json.dumps(block["input"]))
                      for block in content if block.get("type") == "tool_use")
        if not calls:
            return Generation("NO_TOOL_CALL", raw, [], (), incoming, outgoing)
        if len(calls) != 1 or stop != "tool_use":
            raise ValueError("exactly one tool call required")
        return Generation("COMPLETED", raw, content, calls, incoming, outgoing)
    except (ValueError, TypeError, KeyError, AttributeError):
        return Generation("MALFORMED_RESPONSE", raw, [])
