"""Paired single-agent, two-agent and deterministic process-test execution."""

import json

from pydantic import ValidationError
from sqlalchemy import select

from ledgerquant.research import tables as t
from ledgerquant.research.catalog import CATALOG, Diagnostic
from ledgerquant.research.proposals import Proposal, Critique, review
from ledgerquant.research.registry import RegistryError
from ledgerquant.research.types import canonical, digest
from .definitions import definition
from .process_contracts import Assessment, assessment_schema
from .runtime import Runner


def checklist(payload, evidence_ids):
    try:
        proposal = Proposal.model_validate(payload)
    except ValidationError:
        return Assessment(disposition="REJECT", reasons=("UNSUPPORTED_CONTRACT",), explanation="Catalog/schema rejection.", confidence=1)
    critique = Critique(draft_sha256=digest(proposal), disposition="REVIEW", objections=(), summary="Deterministic catalog check only.")
    result = review(proposal, critique, set(evidence_ids), set())
    mapping = {"AWAITING_OPERATOR_REVIEW": "REVIEW", "REJECTED": "REJECT", "BLOCKED_DATA_REQUIREMENT": "BLOCKED_DATA_REQUIREMENT"}
    reasons = ("SUPPORTED_CATALOG",) if result.status == "AWAITING_OPERATOR_REVIEW" else result.reasons
    return Assessment(disposition=mapping[result.status], reasons=reasons, explanation="Fixed catalog checklist; no semantic judgement.", confidence=1)


class ProcessRunner(Runner):
    def run(self, config, command_key, task):
        for role in ("research", "critic"):
            if config["versions"][role] != digest(definition(role, self.provider.profile, "process_review")):
                raise RegistryError("unregistered process binding")
        if task["arm"] not in {"single", "critic", "checklist"} or task["feedback"] not in {"none", "structured"}:
            raise RegistryError("unknown process arm")
        run, created = self.registry.start_run(command_key, config["campaign_id"], config["snapshot_id"],
            config["versions"]["research"], config["versions"]["critic"], task)
        if not created:
            return self.registry.report(run["id"])
        self.step = 0
        try:
            manifest = self.registry.read(self.registry.get(t.snapshots, config["snapshot_id"])["manifest_id"])
            with self.registry.engine.connect() as c:
                invalid = set(c.execute(select(t.evidence_events.c.evidence_id).where(t.evidence_events.c.kind == "INVALIDATED")).scalars())
            if invalid & set(manifest["evidence"]):
                raise RegistryError("SOURCE_REVIEW_REQUIRED")
            context = {"catalog": CATALOG, "known_evidence_ids": sorted(manifest["evidence"]),
                       "known_duplicate_diagnostics": [Diagnostic(hours_utc=[8, 12, 16]).model_dump(mode="json")],
                       "duplicate_rule": "Compare the exact normalized diagnostic, including the complete hours_utc array. A subset is a related variant, not a duplicate solely because its individual hours occur in the old array.",
                       "proposal_defaults": Diagnostic(hours_utc=[8, 12, 16]).model_dump(mode="json"),
                       "proposal": task["proposal"],
                       "feedback_policy": task["feedback"], "evidence_mode": "synthetic_contract_process_test"}
            if task["feedback"] == "structured":
                context["released_evidence"] = {key: self.registry.read(value) for key, value in manifest["evidence"].items()}
            if task["arm"] == "checklist":
                answer = checklist(task["proposal"], manifest["evidence"])
                first = None
            else:
                self._probe(run)
                first = self._assess(run, "research", context)
                answer = self._assess(run, "critic", {**context, "first_assessment": first.model_dump(mode="json")}) if task["arm"] == "critic" else first
            self.registry.event(run["id"], "PROCESS_RESULT", {"answer": answer.model_dump(mode="json"),
                "research_answer": first.model_dump(mode="json") if first else None,
                "authority": "process_assessment_only", "evaluator_measurement": False})
        except (RegistryError, ValueError) as exc:
            self.registry.event(run["id"], "STOPPED", {"reason": str(exc), "economic_failure": False})
        return self.registry.report(run["id"])

    def _assess(self, run, role, context):
        binding = self.registry.read(self.registry.get(t.agent_versions, run[f"{role}_version"])["definition_id"])
        invocation, result = self._invoke(run, role, binding["instructions"],
            [self.provider.user_message(canonical(context))], assessment_schema())
        call = result.calls[0]
        if call.name != "submit_process_assessment":
            raise RegistryError("WRONG_PROCESS_TOOL")
        answer = Assessment.model_validate_json(call.arguments)
        self.registry.record_tool(run["id"], invocation["id"], role, call.name, json.loads(call.arguments), answer.model_dump(mode="json"), True)
        return answer
