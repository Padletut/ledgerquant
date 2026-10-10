"""Research identities and append-only facts; large values are hashed artifacts."""

from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, ForeignKey, Integer, MetaData, String, Table, Text, UniqueConstraint


metadata = MetaData(schema="research")


def ident(name="id", **kwargs):
    return Column(name, String(128), primary_key=True, **kwargs)


def timestamp(name="created_at"):
    return Column(name, DateTime(timezone=True), nullable=False)


def ref(name, table, nullable=False):
    return Column(name, String(128), ForeignKey(f"research.{table}.id"), nullable=nullable)


artifacts = Table("artifacts", metadata, ident(), Column("body", Text, nullable=False), timestamp())
campaigns = Table("campaigns", metadata, ident(), ref("policy_id", "artifacts"), timestamp())
agent_versions = Table("agent_versions", metadata, ident(), Column("role", String(20), nullable=False), ref("definition_id", "artifacts"), timestamp())
snapshots = Table("snapshots", metadata, ident(), ref("manifest_id", "artifacts"), timestamp())
evidence = Table("evidence", metadata, ident(), ref("artifact_id", "artifacts"), ref("contract_id", "artifacts"),
                 Column("family_id", String(100), nullable=False), timestamp("original_registered_at"), timestamp())
evidence_events = Table("evidence_events", metadata, ident(), ref("evidence_id", "evidence"),
                        Column("kind", String(30), nullable=False), ref("detail_id", "artifacts"), timestamp())
windows = Table("window_exposures", metadata, ident(), ref("evidence_id", "evidence"),
                Column("start_at", DateTime(timezone=True), nullable=False),
                Column("end_at", DateTime(timezone=True), nullable=False),
                Column("state", String(20), nullable=False), timestamp())
runs = Table("runs", metadata, ident(), Column("command_key", String(128), nullable=False, unique=True),
             ref("campaign_id", "campaigns"), ref("snapshot_id", "snapshots"),
             ref("research_version", "agent_versions"), ref("critic_version", "agent_versions"),
             ref("task_id", "artifacts"), timestamp())
run_events = Table("run_events", metadata, ident(), ref("run_id", "runs"),
                   Column("kind", String(40), nullable=False), ref("detail_id", "artifacts"), timestamp(),
                   UniqueConstraint("run_id", "kind", name="uq_research_run_event_kind"))
invocations = Table("invocations", metadata, ident(), ref("run_id", "runs"), ref("agent_version", "agent_versions"),
                    ref("request_id", "artifacts"), Column("step", Integer, nullable=False),
                    Column("reserved_tokens", Integer, nullable=False),
                    Column("reserved_micro_usd", BigInteger, nullable=False), timestamp(),
                    CheckConstraint("reserved_tokens > 0 AND reserved_micro_usd >= 0"),
                    UniqueConstraint("run_id", "step", name="uq_research_invocation_step"))
outcomes = Table("invocation_outcomes", metadata, ident(), ref("invocation_id", "invocations"),
                 Column("status", String(40), nullable=False), ref("response_id", "artifacts"),
                 Column("input_tokens", Integer), Column("output_tokens", Integer), timestamp(),
                 UniqueConstraint("invocation_id", name="uq_research_invocation_outcome"))
tool_calls = Table("tool_calls", metadata, ident(), ref("run_id", "runs"),
                   ref("invocation_id", "invocations"), Column("role", String(20), nullable=False),
                   Column("name", String(80), nullable=False), Column("allowed", Integer, nullable=False),
                   ref("arguments_id", "artifacts"), ref("result_id", "artifacts"), timestamp())
drafts = Table("drafts", metadata, ident(), ref("run_id", "runs"),
               Column("family_id", String(100), nullable=False), Column("signature", String(64), nullable=False),
               ref("artifact_id", "artifacts"), timestamp(),
               UniqueConstraint("run_id", name="uq_research_run_draft"))
critiques = Table("critiques", metadata, ident(), ref("draft_id", "drafts"), ref("artifact_id", "artifacts"), timestamp(),
                  UniqueConstraint("draft_id", name="uq_research_draft_critique"))
commitments = Table("commitments", metadata, ident(), ref("draft_id", "drafts"),
                    Column("actor", String(120), nullable=False), Column("kind", String(30), nullable=False),
                    ref("artifact_id", "artifacts"), timestamp(),
                    UniqueConstraint("draft_id", "kind", name="uq_research_commitment_kind"))
# Operator-owned process assessments and derived feedback (architecture 2.14).
# A version supersedes at most one earlier version; nothing is rewritten.
assessments = Table("process_assessments", metadata, ident(), ref("run_id", "runs"),
                    Column("role", String(20), nullable=False), ref("artifact_id", "artifacts"), ref("packet_id", "artifacts"),
                    Column("supersedes_id", String(128), ForeignKey("research.process_assessments.id"), nullable=True),
                    Column("actor", String(120), nullable=False), timestamp(),
                    UniqueConstraint("supersedes_id", name="uq_research_assessment_supersedes"))
feedback = Table("feedback", metadata, ident(), Column("feedback_type", String(30), nullable=False),
                 Column("lineage_key", String(200), nullable=False), ref("artifact_id", "artifacts"),
                 Column("supersedes_id", String(128), ForeignKey("research.feedback.id"), nullable=True),
                 Column("actor", String(120), nullable=False), timestamp("available_at"), timestamp(),
                 UniqueConstraint("supersedes_id", name="uq_research_feedback_supersedes"))
FEEDBACK_TABLES = (assessments, feedback)

WORKER_WRITES = (artifacts, runs, run_events, invocations, outcomes, tool_calls, drafts, critiques)
