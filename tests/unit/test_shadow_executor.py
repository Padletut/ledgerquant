"""Decision-time controls for the first non-trading Executor slice."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from ledgerquant.decision.shadow import ShadowDecision, build_context, validate_decision
from ledgerquant.decision.runner import ShadowRunner
from ledgerquant.decision.shadow import SHADOW_INSTRUCTIONS, SHADOW_TOOL
from ledgerquant.models.generation import Generation, ModelProfile, ToolCall
from ledgerquant.research.types import digest


NOW = datetime(2026, 10, 12, 8, 0, tzinfo=timezone.utc)


def tick(*, age=1, available_age=1, bid="1.10000", ask="1.10010"):
    return {
        "message_id": uuid4(), "symbol": "EURUSD", "kind": "tick",
        "event_at": NOW - timedelta(seconds=age),
        "observed_at": NOW - timedelta(seconds=age),
        "received_at": NOW - timedelta(seconds=available_age),
        "ingested_at": NOW - timedelta(seconds=available_age),
        "bid": Decimal(bid), "ask": Decimal(ask), "quality_flag": "OBSERVED",
    }


def test_context_uses_only_committed_fresh_quotes():
    old, fresh = tick(age=40), tick(age=1)
    context = build_context([old, fresh], "EURUSD", NOW, max_age_seconds=10)
    assert context["status"] == "READY"
    assert context["latest"]["observation_id"] == str(fresh["message_id"])
    assert len(context["quotes"]) == 2
    assert "account_id" not in str(context)
    assert "feed_id" not in str(context)


def test_stale_future_and_crossed_quotes_do_not_make_ready_context():
    assert build_context([tick(age=30)], "EURUSD", NOW, 10)["status"] == "STALE"
    assert build_context([tick(available_age=-1)], "EURUSD", NOW, 10)["status"] == "UNAVAILABLE"
    assert build_context([tick(bid="1.2", ask="1.1")], "EURUSD", NOW, 10)["status"] == "UNAVAILABLE"


def test_signal_requires_citation_and_frozen_horizon():
    source = tick()
    context = build_context([source], "EURUSD", NOW, 10)
    decision = ShadowDecision.model_validate({
        "action": "LONG", "setup_thesis": "Potential continuation",
        "observation_ids": [str(source["message_id"])],
        "invalidation": "Fresh quote reverses the move", "uncertainty": "High",
        "horizon_minutes": 60, "expiry_minutes": 5,
    })
    assert validate_decision(decision, context, 60, 5) == "VALID"
    assert validate_decision(decision.model_copy(update={"observation_ids": [str(uuid4())]}), context, 60, 5) == "UNKNOWN_CITATION"
    assert validate_decision(decision.model_copy(update={"horizon_minutes": 30}), context, 60, 5) == "HORIZON_MISMATCH"


def test_no_signal_and_invalid_context():
    decision = ShadowDecision.model_validate({
        "action": "NO_SIGNAL", "setup_thesis": "No clear setup",
        "observation_ids": [], "invalidation": "", "uncertainty": "High",
        "horizon_minutes": 60, "expiry_minutes": 5,
    })
    assert validate_decision(decision, {"status": "READY", "quotes": []}, 60, 5) == "VALID"
    assert validate_decision(decision, {"status": "STALE", "quotes": []}, 60, 5) == "CONTEXT_NOT_READY"


class FakeStore:
    def __init__(self, rows, profile, scheduled_at):
        self.rows = rows
        self.recorded = []
        self.item = {"id": uuid4(), "feed_id": "private-feed", "symbol": "EURUSD",
                     "scheduled_at": scheduled_at, "config": {
                         "contract_version": "shadow_executor/1",
                         "model_profile": profile.model_dump(mode="json"),
                         "instructions_sha256": digest(SHADOW_INSTRUCTIONS),
                         "tool_schema_sha256": digest(SHADOW_TOOL),
                         "max_start_delay_seconds": 120,
                         "max_quote_age_seconds": 10,
                         "horizon_minutes": 60, "expiry_minutes": 5, "max_usd": 1}}

    def opportunity(self, _):
        return self.item

    def events(self, _):
        return self.recorded

    def quotes(self, *_):
        return self.rows

    def event(self, _, phase, payload):
        self.recorded.append({"phase": phase, "payload": payload})
        return True


class FakeProvider:
    def __init__(self, profile):
        self.profile = profile
        self.calls = 0

    def user_message(self, value):
        return {"role": "user", "content": value}

    def prepare(self, instructions, conversation, tools):
        assert "private-feed" not in str(conversation)
        return {"instructions": instructions, "input": conversation, "tools": tools}

    def invoke(self, request):
        self.calls += 1
        return Generation("COMPLETED", {"model": self.profile.model}, [],
                          (ToolCall("call-1", "submit_shadow_decision", '{"action":"NO_SIGNAL","setup_thesis":"No setup","observation_ids":[],"invalidation":"","uncertainty":"High","horizon_minutes":60,"expiry_minutes":5}'),),
                          10, 20)


def profile():
    return ModelProfile(provider="openai", endpoint="https://api.openai.com/v1/responses",
        model="test-model", max_output_tokens=256, max_request_bytes=10000,
        timeout_seconds=5, max_steps_per_agent=1, input_usd_per_million=1,
        output_usd_per_million=1, max_run_usd=1, price_basis="test",
        knowledge_exposure="test")


def test_runner_records_stale_opportunity_without_model_call():
    p = profile()
    now = datetime.now(timezone.utc)
    store = FakeStore([], p, now - timedelta(seconds=1))
    provider = FakeProvider(p)
    result = ShadowRunner(store, provider).run(store.item["id"])
    assert result["status"] == "UNAVAILABLE"
    assert provider.calls == 0
    assert [event["phase"] for event in store.recorded] == ["STARTED", "FINAL"]
    assert ShadowRunner(store, provider).run(store.item["id"])["status"] == "RECORDED"


def test_runner_records_no_signal_without_order_path():
    p = profile()
    now = datetime.now(timezone.utc)
    row = tick()
    row.update(event_at=now - timedelta(seconds=1), observed_at=now - timedelta(seconds=1),
               received_at=now - timedelta(seconds=1), ingested_at=now - timedelta(seconds=1))
    store = FakeStore([row], p, now - timedelta(seconds=1))
    provider = FakeProvider(p)
    result = ShadowRunner(store, provider).run(store.item["id"])
    assert result["status"] == "NO_SIGNAL"
    assert store.recorded[-1]["payload"]["decision"]["action"] == "NO_SIGNAL"
    assert provider.calls == 1


def test_missed_slot_and_uncertain_start_never_call_provider():
    p = profile()
    store = FakeStore([], p, datetime.now(timezone.utc) - timedelta(minutes=3))
    provider = FakeProvider(p)
    assert ShadowRunner(store, provider).run(store.item["id"])["status"] == "MISSED"
    assert provider.calls == 0
    store.recorded.pop()
    assert ShadowRunner(store, provider).run(store.item["id"])["status"] == "STARTED_UNCERTAIN"
    assert provider.calls == 0


def test_changed_schema_rejected_before_invocation():
    p = profile()
    store = FakeStore([], p, datetime.now(timezone.utc) - timedelta(seconds=1))
    store.item["config"]["tool_schema_sha256"] = "bad"
    provider = FakeProvider(p)
    import pytest
    with pytest.raises(ValueError, match="contract differs"):
        ShadowRunner(store, provider).run(store.item["id"])
    assert provider.calls == 0
