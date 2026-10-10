"""Bounded fresh inference and durable, non-executing recorded-output replay."""

import json

from ledgerquant.research import tables as t
from ledgerquant.research.registry import BudgetExceeded, RegistryError
from ledgerquant.research.repair_exposure import RepairDenied
from ledgerquant.research.ideas import recorded_idea
from ledgerquant.research.types import canonical, digest
from .definitions import definition
from .tools import ResearchTools


PROBE = {"name": "capability_probe", "description": "Return the requested typed conformance answer.",
         "parameters": {"type": "object", "properties": {"answer": {"type": "string", "enum": ["LEDGERQUANT"]}},
                        "required": ["answer"], "additionalProperties": False}}


class Runner:
    def __init__(self, registry, provider):
        self.registry, self.provider = registry, provider
        self.step = 0

    def run(self, config, command_key, task):
        for role in ("research", "critic"):
            if config["versions"][role] != digest(definition(role, self.provider.profile,
                    workflow=config.get("workflow", "discovery"), contract_version=config.get("contract_version", 1))):
                raise RegistryError("runtime definition differs from registered agent version")
        run, created = self.registry.start_run(command_key, config["campaign_id"], config["snapshot_id"],
            config["versions"]["research"], config["versions"]["critic"], task)
        if not created:
            return self.registry.report(run["id"])
        self.step = 0
        try:
            if config.get("contract_version", 1) == 3:
                from ledgerquant.research.grounding import frozen_context
                frozen_context(self.registry, run["id"])
            linked_idea = self._linked_idea(run, config.get("workflow", "discovery"), task)
            self._probe(run)
            self._role(run, "research", {"task": task, **({"linked_idea": linked_idea} if linked_idea else {})})
            draft = self.registry.get(t.drafts, run["id"])
            # Fresh conversation: the draft and authorized tool results, never
            # Research's private conversation or unsupported claims as authority.
            self._role(run, "critic", {"task": task, "draft_sha256": draft["artifact_id"],
                                        "draft": self.registry.read(draft["artifact_id"]),
                                        **({"linked_idea": linked_idea} if linked_idea else {})})
            decision = ResearchTools(self.registry, run["id"], "critic").review()
            self.registry.event(run["id"], "FINISHED", decision)
        except (RegistryError, ValueError) as exc:
            kind = ("BUDGET_EXHAUSTED" if isinstance(exc, BudgetExceeded) else
                    "REPAIR_EXPOSURE_DENIED" if isinstance(exc, RepairDenied) else "ENGINEERING_FAILURE")
            self.registry.event(run["id"], "STOPPED", {"reason": str(exc), "kind": kind,
                "economic_failure": False, "retry_policy": "new_command_new_attempt"})
        return self.registry.report(run["id"])

    def _linked_idea(self, run, workflow, task):
        if not isinstance(task, dict):
            return None
        key = "parent_idea_draft_id" if workflow == "idea_exploration" else "source_idea_draft_id"
        draft_id = task.get(key)
        if draft_id is None:
            return None
        if not isinstance(draft_id, str) or not draft_id:
            raise RegistryError("INVALID_IDEA_REFERENCE")
        with self.registry.engine.connect() as connection:
            linked = recorded_idea(connection, draft_id)
        if workflow != "idea_exploration" and linked["idea"].get("kind") == "PARKED":
            raise RegistryError("PARKED_IDEA_NOT_MEASURABLE")
        if max(linked["created_at"], linked["reviewed_at"]) >= run["created_at"]:
            raise RegistryError("IDEA_NOT_PRIOR_TO_RUN")
        linked.pop("created_at")
        linked.pop("reviewed_at")
        if workflow != "idea_exploration":
            reason = task.get("measurement_mapping_reason")
            if not isinstance(reason, str) or not reason.strip():
                raise RegistryError("MEASUREMENT_MAPPING_REASON_REQUIRED")
            linked["measurement_mapping_reason"] = reason
        return linked

    def _invoke(self, run, role, instructions, conversation, tools):
        request = self.provider.prepare(instructions, conversation, tools)
        invocation = self.registry.reserve_invocation(run["id"], run[f"{role}_version"], self.step, request)
        self.step += 1
        try:
            result = self.provider.invoke(request)
        except Exception as exc:
            # No exception text: transport libraries can include credentials.
            self.registry.complete_invocation(invocation["id"], "DISPATCH_UNKNOWN", {"exception_type": type(exc).__name__})
            raise RegistryError("DISPATCH_UNKNOWN") from None
        self.registry.complete_invocation(invocation["id"], result.status, result.raw, result.input_tokens, result.output_tokens)
        if result.status != "COMPLETED":
            raise RegistryError(result.status)
        if result.input_tokens is None or result.output_tokens is None:
            raise RegistryError("USAGE_UNKNOWN")
        if (result.output_tokens > self.provider.profile.max_output_tokens or
                result.input_tokens > invocation["reserved_tokens"] - self.provider.profile.max_output_tokens):
            raise RegistryError("PROVIDER_EXCEEDED_TOKEN_RESERVATION")
        if len(result.calls) != 1:
            raise RegistryError("ONE_TOOL_CALL_REQUIRED")
        return invocation, result

    def _probe(self, run):
        invocation, result = self._invoke(run, "research", "Call capability_probe with answer LEDGERQUANT.",
            [self.provider.user_message("Verify typed function calling before activating this run.")], [PROBE])
        call = result.calls[0]
        if call.name != PROBE["name"] or json.loads(call.arguments) != {"answer": "LEDGERQUANT"}:
            raise RegistryError("CAPABILITY_CONFORMANCE_FAILED")
        self.registry.event(run["id"], "CAPABILITY_VERIFIED", {"invocation_id": invocation["id"],
            "model_profile_sha256": digest(self.provider.profile), "capability": "bounded_typed_function_calling",
            "does_not_certify": ["factual_correctness", "calibration", "economic_value"]})

    def _role(self, run, role, task):
        binding = self.registry.get(t.agent_versions, run[f"{role}_version"])
        spec = self.registry.read(binding["definition_id"])
        conversation = [self.provider.user_message(canonical(task))]
        tools = ResearchTools(self.registry, run["id"], role)
        for _ in range(self.provider.profile.max_steps_per_agent):
            invocation, result = self._invoke(run, role, spec["instructions"], conversation, tools.schemas())
            conversation.extend(result.continuation)
            call = result.calls[0]
            try:
                arguments = json.loads(call.arguments)
            except ValueError:
                arguments = {"malformed_json": call.arguments}
            response = tools.execute(invocation["id"], call.name, arguments)
            conversation.append(self.provider.tool_result(call.id, canonical(response)))
            if tools.submitted:
                return
        raise RegistryError(f"{role.upper()}_STEP_BUDGET_EXHAUSTED")
