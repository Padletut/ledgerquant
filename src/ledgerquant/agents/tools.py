"""Six bounded research operations; authorization is independent of model text."""

import json

from pydantic import Field, ValidationError
from sqlalchemy import func, select

from ledgerquant.research import tables as t
from ledgerquant.research.catalog import classify
from ledgerquant.research.proposals import Critique, Proposal, review
from ledgerquant.research.scoped_proposals import contract_types, parse_proposal, parse_critique, REQUIREMENT_RULES
from ledgerquant.research.grounding import recorded_context
from ledgerquant.research.contract_revisions import RevisionSubmission, resolve_revision
from ledgerquant.research.registry import RegistryError, append, artifact, now, value
from ledgerquant.research.types import Record, digest


class Empty(Record):
    pass


class Page(Record):
    offset: int = Field(default=0, ge=0, le=10000)
    limit: int = Field(default=10, ge=1, le=20)


OPERATIONS = {
    "read_source_coverage": (Empty, {"research", "critic"}, "Read catalog, source provenance, limits and family counts."),
    "read_released_evidence": (Empty, {"research", "critic"}, "Read both released prior outcomes, including failures."),
    "read_development_snapshot": (Page, {"research", "critic"}, "Read a bounded page from the permitted development view."),
    "submit_hypothesis_draft": (Proposal, {"research"}, "Submit the one typed proposal. This does not freeze or approve it."),
    "submit_critique": (Critique, {"critic"}, "Submit one critique of the supplied exact draft."),
    "request_contract_review": (Empty, {"research", "critic"}, "Request deterministic checks; operator admission remains separate."),
}
REQUIRED_READS = {"read_source_coverage", "read_released_evidence", "read_development_snapshot"}


def operations(version):
    proposal, critique = contract_types(version)
    result = {name: ((proposal if name == "submit_hypothesis_draft" else critique if name == "submit_critique" else schema), roles, description)
              for name, (schema, roles, description) in OPERATIONS.items()}
    if version == 3:
        result["submit_contract_revision"] = (RevisionSubmission, {"research"},
            "Submit one authorized correction of a prior attempt. The service preserves the parent and applies only its permitted cost-scope patch.")
    return result


def schemas(role, contract_version=1):
    return [{"name": name, "description": description, "parameters": schema.model_json_schema()}
            for name, (schema, roles, description) in operations(contract_version).items() if role in roles]


class ResearchTools:
    def __init__(self, registry, run_id, role):
        if role not in {"research", "critic"}:
            raise RegistryError("unknown agent role")
        self.registry, self.run_id, self.role = registry, run_id, role
        run = registry.get(t.runs, run_id)
        binding = registry.read(registry.get(t.agent_versions, run[f"{role}_version"])["definition_id"])
        self.contract_version = binding.get("research_contract_version", 1)
        self.operations = operations(self.contract_version)
        self.submission_policy = registry.read(run["task_id"]).get("submission_policy", "proposal_or_authorized_revision")
        snapshot = registry.get(t.snapshots, run["snapshot_id"])
        self.manifest = registry.read(snapshot["manifest_id"])
        self.reads = set()
        self.submitted = False

    def execute(self, invocation_id, name, arguments):
        invocation = self.registry.get(t.invocations, invocation_id)
        run = self.registry.get(t.runs, self.run_id)
        if invocation["run_id"] != self.run_id or invocation["agent_version"] != run[f"{self.role}_version"]:
            raise RegistryError("TOOL_CALLER_MISMATCH")
        allowed = name in self.operations and self.role in self.operations[name][1]
        with self.registry.engine.begin() as c:
            try:
                with c.begin_nested():
                    if not allowed:
                        raise RegistryError("ROLE_DENIED")
                    parsed = self.operations[name][0].model_validate(arguments)
                    result = self._perform(name, parsed, c)
            except (ValidationError, RegistryError, ValueError) as exc:
                result = {"error": "INVALID_ARGUMENT" if isinstance(exc, ValidationError) else str(exc)}
            self.registry.record_tool(self.run_id, invocation_id, self.role, name, arguments, result, allowed, c)
        if name in REQUIRED_READS and "error" not in result:
            self.reads.add(name)
        return result

    def _released(self, c):
        invalid = set(c.execute(select(t.evidence_events.c.evidence_id)
                               .where(t.evidence_events.c.kind == "INVALIDATED")).scalars())
        return {key: value(c, artifact_id) for key, artifact_id in self.manifest["evidence"].items() if key not in invalid}

    def _perform(self, name, arguments, connection=None):
        if connection is None:
            with self.registry.engine.begin() as c:
                return self._perform(name, arguments, c)
        return self._perform_in_transaction(connection, name, arguments)

    def _perform_in_transaction(self, c, name, arguments):
        if name == "read_source_coverage":
            attempts = c.execute(select(t.drafts.c.id).where(t.drafts.c.family_id == self.manifest["family_id"])).all()
            # This slice accepts only this one family. Count dispatched,
            # malformed, interrupted and rejected runs, not just drafts.
            run_count = c.execute(select(func.count()).select_from(t.runs)).scalar_one()
            result = {"catalog": self.manifest["catalog"], "source": self.manifest["source"],
                    "family_id": self.manifest["family_id"], "legacy_attempts": self.manifest["historical_attempt_count"],
                    "recorded_runs": run_count, "recorded_drafts": len(attempts),
                    "total_family_attempts": self.manifest["historical_attempt_count"] + run_count}
            if self.contract_version == 2:
                result["requirement_rules"] = REQUIREMENT_RULES
                result["recorded_diagnostics"] = [{"draft_id": row.id, "draft_sha256": row.artifact_id,
                    "diagnostic": value(c, row.artifact_id)["diagnostic"]}
                    for row in c.execute(select(t.drafts).where(t.drafts.c.family_id == self.manifest["family_id"]))]
            if self.contract_version == 3:
                result["requirement_rules"] = REQUIREMENT_RULES
                context = recorded_context(c, self.run_id)
                result["prior_inventory"] = {key: context[key] for key in
                    ("version", "cutoff_at", "prior_groups", "unused_catalog_hours", "revision_parents", "exposure", "independence")}
            return result
        if name == "read_released_evidence":
            evidence = self._released(c)
            result = {"evidence": evidence, "invalidated_ids": sorted(set(self.manifest["evidence"]) - set(evidence)),
                      "all_windows_consumed": True}
            if self.contract_version == 3:
                result["facts"] = {key: fact for key, fact in recorded_context(c, self.run_id)["facts"].items()
                                   if fact["evidence_id"] in evidence}
            return result
        if name == "read_development_snapshot":
            if len(self._released(c)) != len(self.manifest["evidence"]):
                raise RegistryError("SOURCE_REVIEW_REQUIRED")
            snapshot = value(c, self.manifest["development_id"])
            cases = snapshot["cases"]
            return {"artifact_id": self.manifest["development_id"], "evidence_mode": "development",
                    "start": snapshot["start_inclusive_utc"], "end": snapshot["end_exclusive_utc"],
                    "total_cases": len(cases), "offset": arguments.offset,
                    "cases": cases[arguments.offset:arguments.offset + arguments.limit]}
        if name.startswith("submit_") and not REQUIRED_READS <= self.reads:
            raise RegistryError("REQUIRED_EVIDENCE_NOT_READ")
        if self.contract_version == 3 and self.submission_policy == "revision_only" and name == "submit_hypothesis_draft":
            raise RegistryError("AUTHORIZED_REVISION_REQUIRED")
        if name == "submit_contract_revision":
            arguments = resolve_revision(arguments, recorded_context(c, self.run_id))
        if name in {"submit_hypothesis_draft", "submit_contract_revision"}:
            family, loop, signature = classify(arguments.diagnostic)
            key = artifact(c, arguments)
            row = append(c, t.drafts, {"id": self.run_id, "run_id": self.run_id, "family_id": family,
                                       "signature": signature, "artifact_id": key, "created_at": now()})
            self.submitted = True
            return {"draft_id": row["id"], "draft_sha256": key, "status": "PROPOSED", "loop": loop}
        draft = c.execute(select(t.drafts).where(t.drafts.c.run_id == self.run_id)).mappings().one_or_none()
        if draft is None:
            raise RegistryError("DRAFT_NOT_SUBMITTED")
        if name == "submit_critique":
            if arguments.draft_sha256 != draft["artifact_id"]:
                raise RegistryError("DRAFT_HASH_MISMATCH")
            append(c, t.critiques, {"id": draft["id"], "draft_id": draft["id"],
                                    "artifact_id": artifact(c, arguments), "created_at": now()})
            self.submitted = True
            return {"critique_id": draft["id"], "status": "CRITIQUE_RECORDED"}
        critique = c.execute(select(t.critiques).where(t.critiques.c.draft_id == draft["id"])).mappings().one_or_none()
        if critique is None:
            return {"status": "AWAITING_CRITIQUE"}
        known = set(c.execute(select(t.drafts.c.signature).where(t.drafts.c.id != draft["id"])).scalars())
        decision = review(parse_proposal(value(c, draft["artifact_id"])),
                          parse_critique(value(c, critique["artifact_id"])), set(self._released(c)), known,
                          recorded_context(c, self.run_id) if self.contract_version == 3 else None)
        return decision.model_dump(mode="json")

    def review(self):
        """The trusted scheduler requests review without impersonating a model call."""
        result = self._perform("request_contract_review", Empty())
        self.registry.event(self.run_id, "CONTRACT_REVIEW", result)
        return result
