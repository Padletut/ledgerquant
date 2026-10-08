# LedgerQuant Architecture Specification Manual

## System Blueprint & Design Framework

**Date:** 08.10.2026
**Version:** 1.1.0 — Architecture Review Revision  
**Classification:** Proprietary Quantitative Infrastructure  
**Status:** Design specification; not a production qualification

## Executive Architectural Summary

LedgerQuant is an isolated, configurable multi-agent research and decision-support platform intended for algorithmic trading of Contract for Difference (CFD) instruments.

The architecture separates market-data ingestion, agent configuration, inference, evaluation, execution authorization and broker-side safety. Agent roles, instruction versions, validation schemas and selected runtime parameters are represented as versioned configuration rather than being embedded throughout the execution codebase.

The runtime should remain comparatively small and generic. Strategy-specific behavior belongs in explicitly versioned configurations, data contracts and model artifacts where practical. This does not imply that all future behavior can or should be expressed as database configuration; safety-critical semantics and invariants remain code-owned.

LedgerQuant is designed around four principles:

**Single Source of Truth (SSOT).**  
Material execution states, agent/prompt versions, model identifiers, validation schemas, source observations and execution outcomes are recorded in a durable PostgreSQL-backed ledger with explicit lineage. Historical records are not silently rewritten when configuration changes.

**Shared Execution Infrastructure.**  
Common agent lifecycle, inference, validation, audit and transport behavior is implemented through reusable execution components. DRY is a design objective, not a requirement to force semantically different agents through inappropriate abstractions.

**Point-in-Time Replay.**  
Historical evaluation exposes only information recorded as available under the replay's declared temporal contract. This reduces lookahead risk but does not by itself guarantee unbiased or production-equivalent historical simulation.

**Controlled Runtime Adaptability.**  
Agent configurations and prompts may be proposed and evaluated without source-code modification or service redeployment where their contracts permit it. Adaptive components may generate candidate configurations, but production promotion remains an explicit governed operation.

---

### 1. High-Level System Topology

LedgerQuant separates four responsibilities:

```text
External Sources
      │
      ▼
┌───────────────────────────────┐
│      Ingestion Workers        │
│ normalization + provenance    │
└───────────────┬───────────────┘
                │
                ▼
┌───────────────────────────────────────────┐
│ PostgreSQL / TimescaleDB / optional       │
│ vector-search storage                     │
│                                           │
│ observations                              │
│ configuration registry                    │
│ inference/audit ledger                    │
│ evaluation results                        │
│ execution reports                         │
└───────────────────┬───────────────────────┘
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
┌─────────────────┐   ┌─────────────────┐
│ Adaptive Runner │   │ FastAPI Gateway │
│ inference       │   │ auth / API / WS │
│ validation      │   └────────┬────────┘
│ replay          │            │ TLS/WS
└─────────────────┘            ▼
                         ┌──────────────┐
                         │ External C# │
                         │ cBot Safety │
                         │ Gateway     │
                         └──────────────┘
```

The database is a persistence and lineage authority. It is **not** automatically the authority for every safety decision. Broker/account state observed by the execution gateway may be newer than database state and must be handled accordingly.

The C# execution component remains independently capable of rejecting an otherwise valid LedgerQuant signal.

---

### 1.1 Signal Lifecycle

A signal follows an auditable state transition sequence:

```text
SOURCE OBSERVATION
       │
       ▼
   INGESTED
       │
       ▼
   ELIGIBLE
       │
       ▼
  EVALUATING
       │
       ├────► REJECTED_VALIDATION
       │
       ▼
   GENERATED
       │
       ▼
   BROADCAST
       │
       ▼
 ACKNOWLEDGED
       │
       ├────► REJECTED_EXECUTION
       │
       ├────► EXPIRED
       │
       ▼
    EXECUTED
       │
       ▼
  RECONCILED
```

Every transition records at minimum:

- immutable signal/correlation identifier;
- event timestamp;
- processing timestamp;
- source/configuration lineage;
- previous and resulting state;
- responsible component;
- structured reason where applicable.

Execution reports are appended as new events or immutable child records. An execution acknowledgement **must not mutate the historical inference event in a way that destroys its original state**.

That distinction is important: append-only audit semantics are incompatible with treating the original row as an ordinary mutable status record.

---

### 2. Data Lineage, Replay and Reproducibility

## 2.1 Canonical Artifact Gateway

External artifacts receive a canonical representation before content identity is calculated.

The canonicalization procedure is **source-type specific and versioned**.

Possible operations include:

1. normalization of explicitly non-semantic transport metadata;
2. canonical field ordering;
3. stable numeric and timestamp serialization;
4. encoding normalization;
5. SHA-256 hashing of canonical bytes.

The original source payload should be retained or independently identifiable whenever legally and operationally practical.

Canonicalization must not silently remove fields merely because they appear irrelevant. A field may later prove semantically meaningful.

Each observation records at least:

```text
source_id
source_type
source_event_time
observed_at
ingested_at
canonicalizer_version
content_sha256
raw_artifact_reference
```

This distinguishes three concepts that the original specification collapsed into `T_ingest`:

\[
T_{event},\quad T_{observed},\quad T_{ingest}
\]

They are not interchangeable.

---

### 2.2 Point-in-Time Visibility

Replay visibility is governed by the timestamp representing when information became available to LedgerQuant under the declared source contract.

Conceptually:

\[
Visible(T)=
\{r\mid r.available\_at\leq T\}
\]

`available_at` must be explicitly defined for each source.

It must **not automatically equal source event time or database insertion time**.

For example, a document describing an event at 14:00 but first observed by LedgerQuant at 14:07 must not become visible in a 14:03 replay merely because the document refers to 14:00.

PIT filtering mitigates temporal lookahead. It does not by itself protect against:

- survivorship bias;
- source revisions;
- unavailable historical representations;
- outcome-conditioned dataset selection;
- changed model/provider behavior;
- incomplete historical source capture;
- execution-model mismatch.

Accordingly, LedgerQuant describes a replay as **PIT-constrained**, not “perfectly historically valid.”

---

### 2.3 Inference Identity and Replay Cache

A replay cache may bypass a new model call only when the complete inference contract matches.

The fingerprint should therefore bind materially relevant inputs such as:

```text
visible_context_hash
prompt_version
system_instruction_version
agent_configuration_version
model/provider identifier
tool configuration
output_schema_version
inference parameters
canonicalization version
```

Conceptually:

\[
F=SHA256(
context
\Vert prompt
\Vert model
\Vert schema
\Vert inference\_contract
)
\]

A matching fingerprint identifies a previously observed inference under that contract.

It does **not** prove that a new probabilistic model invocation would reproduce the same output.

Therefore two replay modes should be distinguished:

**Recorded-output replay**  
Returns the historically recorded output. This is deterministic with respect to the persisted record.

**Fresh-inference replay**  
Invokes the configured model again. Its result may differ and must be stored as a distinct inference event.

This distinction is mandatory in audit output.

---

### 3. Adaptive Agent Architecture

LedgerQuant separates operational inference from configuration research.

```text
                 ┌────────────────────┐
Context ────────►│ Executor Agent     │
                 └─────────┬──────────┘
                           │
                           ▼
                    Candidate Signal
                           │
                           ▼
                    Execution System
                           │
                           ▼
                    Outcome Ledger
                           │
                           ▼
                 ┌────────────────────┐
                 │ Critic / Research  │
                 │ Agent              │
                 └─────────┬──────────┘
                           │
                           ▼
                 Candidate Configuration
                           │
                           ▼
                    Evaluation Pipeline
                           │
                 ┌─────────┴─────────┐
                 ▼                   ▼
              REJECT              CANDIDATE
                                     │
                                     ▼
                              explicit promotion
```

## 3.1 Executor Agent

The Executor performs bounded inference using an explicitly versioned configuration.

During an active evaluation or deployment epoch, its effective contract is immutable.

A registry update does not retroactively alter already-created inference events.

---

### 3.2 Critic Agent

The Critic is a research component, not an execution authority.

It may:

- inspect permitted historical evidence;
- identify recurring failure modes;
- propose prompt/configuration changes;
- generate hypotheses;
- recommend evaluation candidates.

It may **not**:

- directly replace the production configuration;
- modify broker risk authority;
- promote its own candidate because historical metrics improved;
- rewrite historical inference records.

This prevents the Critic from becoming an automated outcome-fitting loop.

---

### 3.3 Candidate Evaluation and Promotion

A proposed configuration follows an explicit lifecycle:

```text
PROPOSED
   ↓
DEVELOPMENT_EVALUATED
   ↓
TEMPORALLY_VALIDATED
   ↓
STRESS_EVALUATED
   ↓
SHADOW / DEMO ELIGIBLE
   ↓
PROSPECTIVE EVIDENCE
   ↓
APPROVED
   ↓
ACTIVE
```

Not every project requires every stage, but any omitted stage must remain visible in configuration status.

Historical improvement alone is insufficient for automatic production promotion.

Promotion is a separately authorized state transition with recorded actor, evidence references and configuration hash.

---

### 4. Polymorphic Registry and Clean Architecture

LedgerQuant stores configurable behavior in a versioned registry while preserving a boundary between **configuration** and **code-owned invariants**.

Configuration may define:

- agent role;
- prompt/instruction version;
- allowed context sources;
- output schema;
- inference model;
- inference parameters;
- evaluation policy;
- deployment status;
- non-safety operational parameters.

Code should continue to own invariants such as:

- authentication enforcement;
- schema validation;
- account/broker reconciliation;
- idempotency;
- execution authorization boundaries;
- hard capital protection;
- transport integrity.

A malformed or malicious database configuration must not be sufficient to disable broker-side safety.

## 4.1 Registry Baseline

The v1.0 draft does not yet contain a complete relational schema. Therefore the architecture is **not yet Alembic-baseline-ready**.

Before the initial migration, define at minimum the identities and relationships for:

```text
agents
agent_versions
prompt_versions
model_contracts
source_contracts
observations
inference_events
signal_events
deployment_epochs
evaluation_runs
execution_reports
promotion_events
```

Append-only tables should be distinguished explicitly from mutable operational projections.

---

### 5. Network Wire Protocol

Communication between LedgerQuant and the external C# execution gateway uses an authenticated, versioned transport.

Every application frame contains a routing envelope:

```json
{
  "meta": {
    "protocol_version": "1.0.0",
    "message_type": "SIGNAL_DISPATCH",
    "message_id": "...",
    "correlation_id": "...",
    "created_at": "...",
    "expires_at": "..."
  },
  "data": {}
}
```

Signals additionally contain the complete identifiers required to establish execution lineage, including:

```text
signal_id
deployment_epoch
agent_version
decision_timestamp
symbol
side
requested execution semantics
risk/execution reference
```

Confidence or regime fields may be transmitted when defined by the active agent schema, but they are **not universal wire-protocol fields**.

---

### 5.1 Idempotency and Ordering

Network delivery must be treated as potentially duplicated, delayed or reordered.

Therefore:

- every message has a globally unique `message_id`;
- execution commands have a stable `signal_id`;
- duplicate execution requests are idempotently rejected or acknowledged;
- expired signals cannot become executable after reconnect;
- acknowledgement does not imply broker fill;
- broker execution is reconciled separately;
- reconnect does not silently replay stale executable commands.

This is more important to capital safety than assuming WebSocket delivery itself is exactly-once.

---

### 5.2 Authentication

`X-Ledger-Auth` may be used as an application authentication mechanism, but transport authentication must not depend on an indefinitely valid plaintext token alone.

The production design should support:

- TLS;
- secret rotation;
- scoped credentials;
- constant-time credential comparison;
- rate limiting;
- connection audit;
- credential revocation.

Database access is never exposed directly through the WebSocket gateway.

---

### 5.3 Heartbeat and Circuit Breaker

Nominal heartbeat:

```text
heartbeat interval: 10 s
acknowledgement target: 2 s
```

These values are operational defaults and configurable within bounded limits, not market guarantees.

After the configured connectivity failure threshold, the execution gateway enters isolation mode:

```text
NEW ENTRIES       → REJECT
PENDING SIGNALS   → INVALIDATE / EXPIRE
OPEN POSITIONS    → retain broker-side protective orders
LOCAL AUDIT       → WRITE
RECONNECT         → require state reconciliation
```

A network outage must **not automatically cause arbitrary trailing modifications to existing positions** unless that behavior is independently specified and tested as part of the position-management policy.

That is an important correction to v1.0.

Connectivity failure and market-risk decisions are separate concerns.

---

### 6. Capital and Execution Authority

The external execution gateway is the final authority over whether a requested action is physically admissible at the broker.

Before entry it verifies, as applicable:

- account identity;
- signal freshness;
- symbol identity;
- current position occupancy;
- market availability;
- executable quote freshness;
- spread/slippage limits;
- requested volume;
- margin availability;
- configured risk limits;
- duplicate/idempotency state.

An agent may propose an action.

**An agent cannot override capital safety.**

Exit/protective-position management must remain possible when the inference service is unavailable.

---

### 7. Observability and Failure Semantics

Every subsystem emits structured state rather than relying solely on free-text logs.

Failures are classified at minimum as:

```text
SOURCE_UNAVAILABLE
SOURCE_STALE
SOURCE_SCHEMA_INVALID
CONTEXT_INCOMPLETE
INFERENCE_FAILED
INFERENCE_SCHEMA_INVALID
SIGNAL_EXPIRED
TRANSPORT_UNAVAILABLE
EXECUTION_REJECTED
BROKER_REJECTED
RECONCILIATION_REQUIRED
```

Infrastructure failure is distinct from a valid agent decision to produce no trade.

Likewise:

```text
NO_SIGNAL != ERROR
REJECTED_RISK != MODEL_FAILURE
NO_FILL != TRANSPORT_FAILURE
```

This distinction is required for meaningful evaluation.

---

### 8. Architectural Guarantees and Non-Guarantees

LedgerQuant is designed to guarantee, subject to correct implementation:

- explicit configuration identity;
- immutable historical inference/audit records;
- source and configuration lineage;
- schema-validated application messages;
- PIT-constrained replay under declared availability semantics;
- explicit execution acknowledgement and reconciliation;
- independent broker-side capital rejection.

LedgerQuant does **not** claim that these mechanisms alone guarantee:

- profitable trading;
- deterministic fresh LLM inference;
- unbiased historical research;
- production-equivalent historical fills;
- optimal prompts;
- correct confidence calibration;
- successful adaptation;
- immunity from data-source errors;
- automatic improvement through Critic iterations.

Those are empirical properties and must be measured separately.

---

### 9. Initial Implementation Sequence

Before generating the entire directory tree, implement one narrow vertical slice:

```text
one source artifact
    ↓
canonical ingestion
    ↓
PIT-visible observation
    ↓
one versioned Executor
    ↓
schema-validated NO_SIGNAL/SIGNAL result
    ↓
append-only inference ledger
    ↓
WS dispatch
    ↓
C# acknowledgement/rejection
    ↓
reconciliation event
```

No Critic is required for this milestone.

Once this path is reproducible and restart-safe, add:

1. recorded-output replay;
2. deployment epochs;
3. evaluation runs;
4. shadow execution;
5. Critic-generated **candidate** configurations;
6. controlled promotion workflow.

This prevents LedgerQuant from beginning life with a sophisticated self-improvement system before it has demonstrated that a single signal can travel through the system without losing identity.

---

### 10. v1.1 Architectural Decision

LedgerQuant should proceed as a **configuration-driven, auditable agent infrastructure**, but the initial implementation should prioritize:

\[
\boxed{\text{lineage} \rightarrow \text{replay} \rightarrow
\text{execution safety} \rightarrow \text{adaptation}}
\]

rather than:

\[
\boxed{\text{adaptation first}}
\]

The Critic is therefore classified as a **candidate generator and research component**, not an autonomous production optimizer.

The database provides authoritative lineage and configuration history, but safety-critical runtime decisions remain independently enforced at the execution boundary.
