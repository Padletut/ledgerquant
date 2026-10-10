"""Transactional research registry, immutable artifacts and resource reservations."""

from datetime import datetime, timezone
from hashlib import sha256
import json
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from ledgerquant.models.budget import micro_usd, reservation
from ledgerquant.models.generation import ModelProfile
from . import tables as t
from .types import canonical


class RegistryError(ValueError):
    pass


class BudgetExceeded(RegistryError):
    pass


def now():
    return datetime.now(timezone.utc)


def append(connection, table, values):
    """Identical command delivery is harmless; a reused identity cannot change facts."""
    connection.execute(insert(table).values(**values).on_conflict_do_nothing())
    row = connection.execute(select(table).where(table.c.id == values["id"])).mappings().one_or_none()
    if row is None or any(row[k] != v for k, v in values.items() if k != "created_at"):
        raise RegistryError(f"conflicting {table.name} identity")
    return dict(row)


def artifact(connection, value, *, raw=False):
    body = value if raw else canonical(value)
    key = sha256(body.encode()).hexdigest()
    append(connection, t.artifacts, {"id": key, "body": body, "created_at": now()})
    return key


def value(connection, key):
    body = connection.execute(select(t.artifacts.c.body).where(t.artifacts.c.id == key)).scalar_one_or_none()
    if body is None or sha256(body.encode()).hexdigest() != key:
        raise RegistryError("artifact absent or corrupt")
    return json.loads(body)


class Registry:
    def __init__(self, engine):
        self.engine = engine

    def get(self, table, key):
        with self.engine.connect() as c:
            row = c.execute(select(table).where(table.c.id == key)).mappings().one_or_none()
            if row is None:
                raise RegistryError(f"unknown {table.name} identity")
            return dict(row)

    def read(self, key):
        with self.engine.connect() as c:
            return value(c, key)

    def start_run(self, command_key, campaign_id, snapshot_id, research_version, critic_version, task):
        with self.engine.begin() as c:
            campaign = c.execute(select(t.campaigns).where(t.campaigns.c.id == campaign_id).with_for_update()).mappings().one()
            task_id = artifact(c, task)
            values = {"campaign_id": campaign_id, "snapshot_id": snapshot_id, "research_version": research_version,
                      "critic_version": critic_version, "task_id": task_id}
            old = c.execute(select(t.runs).where(t.runs.c.command_key == command_key)).mappings().one_or_none()
            if old:
                if any(old[k] != v for k, v in values.items()):
                    raise RegistryError("command key reused for different run")
                return dict(old), False
            policy = value(c, campaign["policy_id"])
            spent = c.execute(select(func.count()).select_from(t.runs).where(t.runs.c.campaign_id == campaign_id)).scalar_one()
            if spent >= policy["max_runs"]:
                raise BudgetExceeded("campaign run budget exhausted")
            for version, role in ((research_version, "research"), (critic_version, "critic")):
                actual = c.execute(select(t.agent_versions.c.role).where(t.agent_versions.c.id == version)).scalar_one_or_none()
                if actual != role:
                    raise RegistryError("agent role mismatch")
            row = append(c, t.runs, {"id": str(uuid4()), "command_key": command_key, **values, "created_at": now()})
            return row, True

    def reserve_invocation(self, run_id, version, step, request):
        with self.engine.begin() as c:
            run = c.execute(select(t.runs).where(t.runs.c.id == run_id)).mappings().one()
            campaign = c.execute(select(t.campaigns).where(t.campaigns.c.id == run["campaign_id"]).with_for_update()).mappings().one()
            if version not in (run["research_version"], run["critic_version"]):
                raise RegistryError("unregistered model binding")
            definition_id = c.execute(select(t.agent_versions.c.definition_id).where(t.agent_versions.c.id == version)).scalar_one()
            profile = ModelProfile.model_validate(value(c, definition_id)["model_profile"])
            reserved_tokens, reserved_money = reservation(profile, request)
            policy = value(c, campaign["policy_id"])
            costs = c.execute(select(func.count(), func.coalesce(func.sum(t.invocations.c.reserved_tokens), 0),
                                     func.coalesce(func.sum(t.invocations.c.reserved_micro_usd), 0))
                              .select_from(t.invocations.join(t.runs, t.invocations.c.run_id == t.runs.c.id))
                              .where(t.runs.c.campaign_id == run["campaign_id"])).one()
            if reserved_tokens <= 0 or costs[0] >= policy["max_invocations"] or costs[1] + reserved_tokens > policy["max_reserved_tokens"]:
                raise BudgetExceeded("campaign invocation/token budget exhausted")
            run_money = c.execute(select(func.coalesce(func.sum(t.invocations.c.reserved_micro_usd), 0))
                                  .where(t.invocations.c.run_id == run_id)).scalar_one()
            if costs[2] + reserved_money > micro_usd(policy["max_usd"]) or run_money + reserved_money > micro_usd(profile.max_run_usd):
                raise BudgetExceeded("monetary reservation exhausted")
            return append(c, t.invocations, {"id": str(uuid4()), "run_id": run_id, "agent_version": version,
                                            "step": step, "request_id": artifact(c, request),
                                            "reserved_tokens": reserved_tokens, "reserved_micro_usd": reserved_money, "created_at": now()})

    def complete_invocation(self, invocation_id, status, response, input_tokens=None, output_tokens=None):
        with self.engine.begin() as c:
            return append(c, t.outcomes, {"id": invocation_id, "invocation_id": invocation_id, "status": status,
                                        "response_id": artifact(c, response), "input_tokens": input_tokens,
                                        "output_tokens": output_tokens, "created_at": now()})

    def event(self, run_id, kind, detail):
        with self.engine.begin() as c:
            return append(c, t.run_events, {"id": f"{run_id}:{kind}", "run_id": run_id, "kind": kind,
                                          "detail_id": artifact(c, detail), "created_at": now()})

    def record_tool(self, run_id, invocation_id, role, name, arguments, result, allowed, connection=None):
        if connection is None:
            with self.engine.begin() as c:
                return self.record_tool(run_id, invocation_id, role, name, arguments, result, allowed, c)
        return append(connection, t.tool_calls, {"id": str(uuid4()), "run_id": run_id, "invocation_id": invocation_id,
                      "role": role, "name": name, "allowed": int(allowed),
                      "arguments_id": artifact(connection, arguments), "result_id": artifact(connection, result), "created_at": now()})

    def report(self, run_id):
        run = self.get(t.runs, run_id)
        with self.engine.connect() as c:
            events = c.execute(select(t.run_events).where(t.run_events.c.run_id == run_id).order_by(t.run_events.c.created_at)).mappings().all()
            calls = c.execute(select(t.invocations).where(t.invocations.c.run_id == run_id).order_by(t.invocations.c.step)).mappings().all()
            invocation_records = []
            for call in calls:
                outcome = c.execute(select(t.outcomes).where(t.outcomes.c.invocation_id == call["id"])).mappings().one_or_none()
                invocation_records.append({**dict(call), "request": value(c, call["request_id"]),
                    "outcome": ({**dict(outcome), "response": value(c, outcome["response_id"])} if outcome else None)})
            tool_records = c.execute(select(t.tool_calls).where(t.tool_calls.c.run_id == run_id).order_by(t.tool_calls.c.created_at)).mappings()
            manifest = value(c, c.execute(select(t.snapshots.c.manifest_id).where(t.snapshots.c.id == run["snapshot_id"])).scalar_one())
            invalid = set(c.execute(select(t.evidence_events.c.evidence_id).where(t.evidence_events.c.kind == "INVALIDATED")).scalars())
            process_invalid = any(event["kind"] == "PROCESS_CONTEXT_INVALIDATED" for event in events)
            correction = c.execute(select(t.commitments.c.artifact_id).where(t.commitments.c.draft_id == run_id,
                t.commitments.c.kind == "CONTRACT_REVIEW_CORRECTION")).scalar_one_or_none()
            draft = c.execute(select(t.drafts).where(t.drafts.c.run_id == run_id)).mappings().one_or_none()
            critique = (c.execute(select(t.critiques).where(t.critiques.c.draft_id == draft["id"])).mappings().one_or_none()
                        if draft is not None else None)
            commitments = (c.execute(select(t.commitments).where(t.commitments.c.draft_id == draft["id"])
                .order_by(t.commitments.c.created_at, t.commitments.c.id)).mappings().all() if draft is not None else [])
            return {"run": run, "events": [{"kind": e["kind"], "detail": value(c, e["detail_id"])} for e in events],
                    "invocations": invocation_records, "tools": [{**dict(row), "arguments": value(c, row["arguments_id"]),
                        "result": value(c, row["result_id"])} for row in tool_records], "mode": "recorded_output_replay",
                    "research_records": {"draft": ({"sha256": draft["artifact_id"], "body": value(c, draft["artifact_id"])} if draft else None),
                                         "critique": ({"sha256": critique["artifact_id"], "body": value(c, critique["artifact_id"])} if critique else None),
                                         "commitments": [{"kind": row["kind"], "actor": row["actor"],
                                                          "sha256": row["artifact_id"], "body": value(c, row["artifact_id"])}
                                                         for row in commitments]},
                    "current_integrity": {"status": "INVALID" if process_invalid else "REVIEW_REQUIRED" if correction or invalid & set(manifest["evidence"]) else "UNCHANGED",
                                          "invalidated_dependencies": sorted(invalid & set(manifest["evidence"])),
                                          **({"contract_review_correction": value(c, correction)} if correction else {})}}
