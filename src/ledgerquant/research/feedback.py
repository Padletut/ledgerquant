"""Typed research feedback: method lessons, empirical findings and untested conjectures."""

from typing import Literal

from pydantic import Field, model_validator
from sqlalchemy import select

from . import tables as t
from .process_assessment import assessment_state
from .registry import RegistryError, append, artifact, now, value
from .types import Record, digest


FEEDBACK_VERSION = "research_feedback/1"
FEEDBACK_TYPES = Literal["METHOD_LESSON", "EMPIRICAL_FINDING", "CAUSAL_CONJECTURE"]
POLICY_VERSION = "reviewed_method_feedback/1"
ARMS = {"HISTORY_ONLY": "no derived feedback; prior inventory and released facts only",
        "HISTORY_PLUS_REVIEWED_METHODS": "released, reviewed feedback selected by a versioned policy before model input"}


class Source(Record):
    kind: Literal["PROCESS_ASSESSMENT", "EVIDENCE", "OBSERVATION"]
    id: str = Field(min_length=1, max_length=200)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class Feedback(Record):
    feedback_type: FEEDBACK_TYPES
    claim: str = Field(min_length=1, max_length=1500)
    applicability: str = Field(min_length=1, max_length=1000)
    counterexamples: tuple[str, ...] = Field(max_length=8)
    sources: tuple[Source, ...] = Field(min_length=1, max_length=8)
    proposed_test: str | None = Field(default=None, min_length=1, max_length=1500)
    untested: bool | None = None
    author: str = Field(min_length=1, max_length=120)
    reviewer: str | None = Field(default=None, min_length=1, max_length=120)
    supersedes: str | None = Field(default=None, min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def type_specific_shape(self):
        kinds = {source.kind for source in self.sources}
        if self.feedback_type == "METHOD_LESSON" and kinds != {"PROCESS_ASSESSMENT"}:
            raise ValueError("a method lesson derives only from process assessments")
        if self.feedback_type == "EMPIRICAL_FINDING" and kinds != {"EVIDENCE"}:
            raise ValueError("an empirical finding derives only from released evaluator evidence")
        if self.feedback_type == "CAUSAL_CONJECTURE" and (self.untested is not True or not self.proposed_test):
            raise ValueError("a conjecture is explicitly untested and names a discriminating test")
        if self.feedback_type != "CAUSAL_CONJECTURE" and (self.untested or self.proposed_test):
            raise ValueError("only a conjecture carries the untested marker and proposed test")
        return self


class FeedbackPolicy(Record):
    version: Literal["reviewed_method_feedback/1"]
    allowed_types: tuple[FEEDBACK_TYPES, ...] = Field(min_length=1, max_length=3)
    include_conjectures: bool = False
    context_limit: int = Field(ge=1, le=20)

    @model_validator(mode="after")
    def conjectures_are_opt_in(self):
        if "CAUSAL_CONJECTURE" in self.allowed_types and not self.include_conjectures:
            raise ValueError("conjectures are excluded from established-method feedback unless explicitly included")
        if self.include_conjectures and "CAUSAL_CONJECTURE" not in self.allowed_types:
            raise ValueError("include_conjectures requires CAUSAL_CONJECTURE among allowed types")
        return self


def _lineage_key(command: Feedback, connection):
    if command.feedback_type == "METHOD_LESSON":
        runs = sorted({connection.execute(select(t.assessments.c.run_id).where(t.assessments.c.id == source.id)).scalar_one()
                       for source in command.sources})
        return "process:" + "+".join(runs)
    if command.feedback_type == "EMPIRICAL_FINDING":
        return "evidence:" + "+".join(sorted(source.id for source in command.sources))
    return "conjecture:" + digest([source.model_dump(mode="json") for source in command.sources])


def record_feedback(registry, command: Feedback):
    with registry.engine.begin() as c:
        agents = set(c.execute(select(t.agent_versions.c.id)).scalars())
        if command.author in agents or command.reviewer in agents:
            raise RegistryError("SELF_CERTIFICATION_REJECTED")
        scope = []
        for source in command.sources:
            if source.kind == "PROCESS_ASSESSMENT":
                row = c.execute(select(t.assessments).where(t.assessments.c.id == source.id)).mappings().one_or_none()
                if row is None or row["artifact_id"] != source.sha256:
                    raise RegistryError("SOURCE_ASSESSMENT_UNKNOWN")
                state = assessment_state(c, source.id)
                if command.feedback_type == "METHOD_LESSON" and state["state"] != "CURRENT":
                    raise RegistryError("METHOD_LESSON_REQUIRES_REVIEWED_CURRENT_ASSESSMENT:" + ",".join(state["reasons"]))
            elif source.kind == "EVIDENCE":
                row = c.execute(select(t.evidence).where(t.evidence.c.id == source.id)).mappings().one_or_none()
                if row is None or row["artifact_id"] != source.sha256:
                    raise RegistryError("SOURCE_EVIDENCE_UNKNOWN")
                if c.execute(select(t.evidence_events.c.id).where(t.evidence_events.c.evidence_id == source.id,
                                                                   t.evidence_events.c.kind == "INVALIDATED")).scalar_one_or_none():
                    raise RegistryError("SOURCE_EVIDENCE_INVALIDATED")
                evidence = value(c, row["artifact_id"])
                contract = value(c, row["contract_id"])
                scope.append({"evidence_id": source.id, "evidence_sha256": source.sha256, "contract_sha256": row["contract_id"],
                              "gate_decision": evidence.get("gate_decision"), "evidence_mode": evidence.get("evidence_mode"),
                              "economic_claim": evidence.get("economic_claim"),
                              "validation_windows": [{key: window[key] for key in ("start_inclusive_utc", "end_exclusive_utc")}
                                                     for window in contract["validation_windows"]],
                              "baseline": contract["payoff_contract"]["baseline"]})
            else:
                if c.execute(select(t.artifacts.c.id).where(t.artifacts.c.id == source.sha256)).scalar_one_or_none() is None:
                    raise RegistryError("SOURCE_OBSERVATION_UNKNOWN")
        if command.supersedes:
            prior = c.execute(select(t.feedback).where(t.feedback.c.id == command.supersedes)).mappings().one_or_none()
            if prior is None or prior["feedback_type"] != command.feedback_type:
                raise RegistryError("SUPERSEDED_FEEDBACK_MISMATCH")
            if c.execute(select(t.feedback.c.id).where(t.feedback.c.supersedes_id == prior["id"])).scalar_one_or_none():
                raise RegistryError("ALREADY_SUPERSEDED")
        lineage = _lineage_key(command, c)
        detail = {"version": FEEDBACK_VERSION, **command.model_dump(mode="json"), "lineage_key": lineage,
                  "evidence_scope": scope, "release_state": "RELEASED" if command.reviewer else "PROPOSED"}
        identity = digest(detail)
        row = append(c, t.feedback, {"id": identity, "feedback_type": command.feedback_type, "lineage_key": lineage,
                                     "artifact_id": artifact(c, detail), "supersedes_id": command.supersedes,
                                     "actor": command.author, "available_at": now(), "created_at": now()})
        return {"feedback_id": identity, "feedback_sha256": row["artifact_id"], "lineage_key": lineage,
                "release_state": detail["release_state"], "available_at": row["available_at"].isoformat()}


def feedback_state(connection, row):
    """Derived release state; source corrections suspend dependent feedback until re-reviewed."""
    c = connection
    detail = value(c, row["artifact_id"])
    reasons = []
    if detail["release_state"] != "RELEASED":
        reasons.append("NOT_REVIEWED")
    if c.execute(select(t.feedback.c.id).where(t.feedback.c.supersedes_id == row["id"])).scalar_one_or_none():
        reasons.append("SUPERSEDED")
    for source in detail["sources"]:
        if source["kind"] == "PROCESS_ASSESSMENT":
            state = assessment_state(c, source["id"])
            reasons.extend("SOURCE_" + reason if not reason.startswith("SOURCE_") else reason for reason in state["reasons"])
        elif source["kind"] == "EVIDENCE":
            if c.execute(select(t.evidence_events.c.id).where(t.evidence_events.c.evidence_id == source["id"],
                                                               t.evidence_events.c.kind == "INVALIDATED")).scalar_one_or_none():
                reasons.append("SOURCE_EVIDENCE_INVALIDATED")
    return {"state": "RELEASED" if not reasons else "SUSPENDED", "reasons": list(dict.fromkeys(reasons))}


def select_feedback(connection, policy: FeedbackPolicy, cutoff):
    """Policy-filtered, lineage-grouped selection with an exact manifest; enforced before model input."""
    c = connection
    rows = c.execute(select(t.feedback).where(t.feedback.c.available_at <= cutoff, t.feedback.c.feedback_type.in_(policy.allowed_types))
                     .order_by(t.feedback.c.available_at, t.feedback.c.id)).mappings().all()
    selected, excluded, seen = [], [], set()
    for row in rows:
        state = feedback_state(c, row)
        if state["state"] != "RELEASED":
            excluded.append({"id": row["id"], "reasons": state["reasons"]})
            continue
        if row["lineage_key"] in seen:
            excluded.append({"id": row["id"], "reasons": ["SAME_ROOT_LINEAGE_ALREADY_SELECTED"]})
            continue
        if len(selected) >= policy.context_limit:
            excluded.append({"id": row["id"], "reasons": ["CONTEXT_LIMIT"]})
            continue
        seen.add(row["lineage_key"])
        detail = value(c, row["artifact_id"])
        selected.append({"id": row["id"], "sha256": row["artifact_id"], "feedback_type": row["feedback_type"],
                         "lineage_key": row["lineage_key"], "available_at": row["available_at"].isoformat(),
                         "claim": detail["claim"], "applicability": detail["applicability"],
                         "counterexamples": detail["counterexamples"], "untested": row["feedback_type"] == "CAUSAL_CONJECTURE",
                         **({"proposed_test": detail["proposed_test"]} if row["feedback_type"] == "CAUSAL_CONJECTURE" else {})})
    manifest = {"policy": policy.model_dump(mode="json"), "cutoff_at": cutoff.isoformat(),
                "selected": [{key: item[key] for key in ("id", "sha256", "feedback_type", "lineage_key")} for item in selected],
                "excluded": excluded, "assembled_input_sha256": digest(selected),
                "independence": "Items sharing a root lineage were collapsed; selection is not independent evidence."}
    return selected, manifest
