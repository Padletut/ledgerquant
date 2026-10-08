# LedgerQuant Architecture

**Date:** 08.10.2026

**Version:** 2.0.0

**Status:** Target architecture; implementation is not yet present in this repository

## 1. Purpose and design rules

LedgerQuant is an auditable, configurable platform for research, decision support and controlled execution of CFD trading strategies. Operators must be able to define, change, activate, pause and retire agents, portfolio profiles and trading accounts through supported workflows. Every trading decision must retain the exact configuration and information that produced it.

- **Explicit ownership:** agent, portfolio, account, market data, decision and execution concepts have distinct owners and contracts.
- **Single source of truth (SSOT):** versioned configuration and audit history live in the registry and ledger. Current broker positions, balances and fills come from the broker and are reconciled into the ledger. Cached views are rebuildable.
- **Reusable behavior:** common lifecycle, validation, persistence and transport behavior is shared through cohesive components. Agent-specific decision logic uses a defined capability interface.
- **Immutable history:** published configuration versions, decision inputs, inference outputs and execution events are never silently rewritten. Changes create new versions or events.
- **Execution safety:** agents propose actions; the account execution gateway independently enforces broker and capital constraints.
- **Incremental distribution:** components have stable boundaries and can run in separate processes or hosts. Deployment is split where isolation, throughput or availability warrants it.
- **Focused modules:** business rules belong in domain and application modules, adapters handle external systems, and entry points only assemble components.

Configuration provides adaptability within a supported contract. A new agent using existing capabilities can be registered without source changes. A genuinely new capability, broker protocol or safety rule requires a reviewed implementation, contract tests and deployment. Arbitrary code stored in the database is not an extension mechanism.

## 2. Logical architecture

```text
                 ┌───────────────────────────────────────┐
                 │ Control API and configuration registry│
                 │ agents · portfolios · accounts        │
                 │ deployments · approvals · read models │
                 └───────────────────┬───────────────────┘
                                     │ versioned commands/events
              ┌──────────────────────┴──────────────────────┐
              │                                             │
              ▼                                             ▼
    ┌──────────────────┐                         ┌──────────────────┐
    │ Ingestion workers│                         │ Scheduler        │
    │ normalization    │                         │ deployment epochs│
    │ provenance       │                         │ account routing  │
    └────────┬─────────┘                         └────────┬─────────┘
             │                                            │
             └────────────────┐              ┌────────────┘
                              ▼              ▼
                         ┌────────────────────────┐
                         │ Decision workers       │
                         │ context · agents       │
                         │ validation · replay    │
                         └───────────┬────────────┘
                                     │ candidate decisions
                                     ▼
                         ┌────────────────────────┐
                         │ Execution coordinator  │
                         │ account serialization  │
                         │ reservations · outbox  │
                         └───────────┬────────────┘
                                     │ authenticated commands
                                     ▼
                         ┌────────────────────────┐
                         │ C# account gateway     │
                         │ independent risk checks│
                         │ broker reconciliation  │
                         └───────────┬────────────┘
                                     ▼
                                   Broker

    PostgreSQL: versioned registry, observations, ledger, outbox and projections
```

The boxes are logical responsibilities, not a requirement for one service per box. The initial deployment may use one control API process, separate workers and the external C# gateway. The API is one logical, versioned surface and may have multiple stateless replicas. There is no API instance or endpoint set per agent. Workers and gateways scale independently, with work partitioned by account where ordering or capital safety requires it.

The control plane manages definitions and deployment intent. The data plane ingests observations and builds point-in-time context. The decision plane runs configured agents. The execution plane owns order authorization, dispatch and reconciliation. A component accesses another component's state through its contract; it does not bypass ownership with ad hoc cross-module database writes.

## 3. Domain model and sources of truth

| Entity | Identity and versioning | Owner and purpose |
| --- | --- | --- |
| `agent_definition` | Stable `agent_id`; immutable `agent_version` | Agent registry. Defines a supported role/capability, input policy, output schema, model and instruction references. |
| `portfolio_profile` | Stable `portfolio_id`; immutable `portfolio_version` | Portfolio registry. Defines investment universe, allocation and risk policy. |
| `trading_account` | Stable `account_id`; operational changes have audit events | Account registry. Identifies broker, environment, external account key, capabilities and credential reference. |
| `portfolio_account_allocation` | Versioned portfolio/account binding | Portfolio registry. Reserves a capital/risk slice and effective interval. |
| `deployment` | Stable `deployment_id`; immutable `deployment_version` and `epoch_id` | Deployment registry. Binds an agent version to a portfolio version, account allocation, schedule, mode and limits. |
| `observation` | Immutable source artifact identity | Market-data owner. Carries source, timing, canonicalization and provenance. |
| `decision` | Immutable `decision_id` and input fingerprint | Decision ledger. Captures the agent result and complete effective configuration. |
| `signal` | Stable `signal_id` | Execution coordinator. Represents one proposed account-scoped trading action. |
| `execution_event` | Immutable event identity | Execution ledger. Records dispatch, gateway response, broker events and reconciliation. |

Identifiers are opaque and remain stable across renames. Display names are never routing keys. Every active deployment resolves to one exact agent version, portfolio version, allocation version and account ID before evaluation. These references are copied into decision and signal lineage. A later registry edit cannot change an in-flight decision.

The broker is authoritative for actual orders, fills, positions, balances and margin. LedgerQuant records the last observed broker state with observation time and reconciliation status. Configuration and intended limits are authoritative in the registry; the C# gateway independently checks live broker state before execution.

### 3.1 Agent definitions and lifecycle

An agent definition contains a stable ID, role, capability identifier, input/context contract, output schema, model/provider contract when applicable, instruction or artifact references, allowed tools, resource limits and evaluation policy. A version is immutable after publication. The same runner executes any version that satisfies a registered capability interface and validated schema.

```text
DRAFT → VALIDATED → CANDIDATE → APPROVED → ACTIVE → PAUSED → RETIRED
                       └───────────────→ REJECTED
```

- **Create:** validate references, supported capability, schema compatibility, permissions and resource bounds before publishing a version.
- **Change:** create a new version. Run contract and evaluation checks, then promote it explicitly. Existing epochs keep their pinned version.
- **Pause:** stop new scheduling and dispatch for affected deployments; reconcile existing broker work according to the execution policy.
- **Retire:** prevent new deployments and retain all versions and lineage. Referenced definitions are never physically deleted from history.
- **Remove a draft:** allow deletion only before it has been referenced by an event or published version.

An agent may emit `NO_SIGNAL`, a typed candidate action or a structured failure. Output validation occurs before signal creation. An Executor is a decision capability. A Critic is a research capability that may propose candidate versions but has no authority to activate deployments or change capital limits. Additional capabilities use the same lifecycle and typed interfaces; their behavior is not encoded in a growing role-specific switch statement.

### 3.2 Portfolio profiles and account allocations

A portfolio profile is a reusable policy, not a broker account. Its version defines eligible instruments and markets, capital budget, exposure and concentration limits, strategy allocation rules, rebalance or evaluation schedule, and allowed execution modes. Constraints are typed, validated and have explicit units and currencies. Values that affect risk or selection are frozen into the version used by a deployment.

An allocation binds a portfolio profile to a trading account for an effective interval and assigns an explicit capital/risk slice. A profile may span accounts; an account may serve multiple profiles when allocations are compatible. Activation checks that account-wide limits and reserved slices are not exceeded. Runtime risk checks aggregate across all active allocations and deployments on the same account. Where constraints conflict, the stricter applicable limit wins. No agent or profile can loosen an account-level hard limit.

Changing portfolio policy creates a new portfolio version and a controlled deployment transition. Changing the allocation creates a new binding version. Removing an active binding first drains or pauses dependent deployments, resolves pending orders and preserves historical bindings for audit. Renaming a profile does not alter its identity.

### 3.3 Trading accounts

A trading account records broker adapter type, environment, external account key, base currency, allowed instruments, execution capabilities, status and a reference to credentials in a secret store. Raw credentials never enter agent configuration, API responses, audit payloads or source control. Credential rotation changes the reference and records an audit event without changing account identity.

Account states are `DRAFT`, `VERIFIED`, `ACTIVE`, `SUSPENDED` and `RETIRED`. Verification includes broker identity and capability checks. Suspension rejects new entries while preserving broker-side position protection and reconciliation. Retirement requires disabled deployments, no unresolved commands and an explicit position handover policy. Historic accounts and their execution records remain queryable. The same external broker account must not be registered twice in the same environment unless an explicit shared-account policy and serialized execution owner are configured.

### 3.4 Deployments and safe reconfiguration

A deployment binds a published agent version, portfolio version, allocation, account, execution mode (`RESEARCH`, `SHADOW`, `DEMO` or `LIVE`) and schedule. Activation creates an immutable epoch with a content hash of all effective configuration. Multiple deployments can run concurrently; each result is attributed to its deployment and epoch. A new version becomes effective only at a declared epoch boundary. The scheduler receives a registry change event and periodically reconciles its state against the registry so a missed notification cannot leave it permanently stale.

Before activation, validate schema compatibility, account capability, market permissions, allocation capacity, risk limits, credential availability and required approvals. Version transitions are atomic at the deployment level. In-flight evaluations complete under their original epoch; new work uses the new epoch. Conflicting simultaneous changes use optimistic concurrency and return a conflict rather than silently overwriting another operator's edit.

## 4. Decision and execution flow

Source ingestion, decision making and broker execution have separate event histories. An observation is not a signal state, and a gateway acknowledgement is not a fill.

```text
Observation → PIT context → pinned deployment epoch → validated agent result
                                                     ├─ NO_SIGNAL
                                                     ├─ FAILURE
                                                     └─ candidate action
                                                             ↓
                                           account-wide policy and reservation
                                                             ↓
                                                 signal and dispatch outbox
                                                             ↓
                                             C# gateway checks live account
                                                             ↓
                                          broker order / rejection / timeout
                                                             ↓
                                                  reconciliation events
```

Decision events record input observation IDs, context hash, agent and portfolio versions, allocation and account IDs, epoch, model and instruction versions, output schema, result, timestamps and reason codes. A candidate action becomes executable only after policy checks, account capacity reservation and durable dispatch intent succeed.

The signal workflow is `CREATED → AUTHORIZED → DISPATCHED → ACKNOWLEDGED → BROKER_ACCEPTED → PARTIALLY_FILLED/FILLED → RECONCILED`, with explicit `REJECTED`, `EXPIRED`, `CANCELLED` and `UNKNOWN_PENDING_RECONCILIATION` paths. Transitions are appended as events; a current-status projection may be updated for queries. A timeout leaves uncertain broker state to reconcile before retrying an order. Every command uses a stable `signal_id` and an idempotency key. Retries must not create a second broker order.

Per-account execution is serialized through one logical owner or an equivalent fenced lease. The coordinator checks aggregate reserved exposure across all deployments on that account, then records the reservation and an outbox message in one database transaction. If the owner changes, fencing prevents the previous owner from dispatching new commands. The C# gateway remains independently capable of rejecting a command based on fresher broker state. Reconciliation releases or adjusts reservations from observed broker outcomes.

### 4.1 Wire contract and connection safety

The authenticated, versioned gateway protocol uses a routing envelope with `protocol_version`, `message_type`, `message_id`, `correlation_id`, `account_id`, `created_at` and `expires_at`. A trading command also carries `signal_id`, `deployment_id`, `epoch_id`, agent and portfolio version IDs, instrument, side, order semantics and applicable risk-policy reference. Optional agent output fields are part of the agent schema, not universal protocol fields.

Delivery may be duplicated, delayed or reordered. The gateway persists command idempotency and reports acknowledgements separately from broker acceptance and fills. Expired commands cannot be executed after reconnect. After a connectivity failure threshold, new entries stop, pending commands are invalidated or reconciled, and existing protective orders remain under gateway and broker control. Reconnection requires account and order reconciliation before new entries resume.

Transport uses TLS, scoped and revocable credentials, rotation, rate limits and connection audit. The gateway receives only the account-scoped commands it is authorized to execute. The control API cannot bypass gateway risk checks.

## 5. Data lineage and replay

Each external artifact is normalized by a source-specific, versioned canonicalizer before its content hash is calculated. Preserve the original payload or an immutable reference where legally and operationally possible. Canonicalization records what was normalized; it cannot discard fields merely because they appear irrelevant.

An observation records `source_id`, `source_type`, `source_event_time`, `observed_at`, `ingested_at`, `available_at`, `canonicalizer_version`, `content_sha256` and `raw_artifact_reference`. `available_at` is defined by the source contract and controls point-in-time visibility. It does not automatically equal event time or insertion time. Replay at time `T` may read only records whose declared `available_at ≤ T` and whose source revisions were visible then.

An inference fingerprint binds the visible context, canonicalization version, agent and portfolio versions, model/provider, instructions, tools, output schema and inference parameters. Recorded-output replay returns the persisted result for that exact contract. Fresh-inference replay invokes the model again and stores a distinct event; probabilistic inference may differ. Replay results state the mode and the source-availability contract.

Point-in-time filtering alone does not eliminate survivorship bias, missing historical observations, changed providers or execution-model differences. Evaluation reports identify these limits and keep research, shadow, demo and live results separate.

## 6. Persistence and consistency

PostgreSQL is the initial durable store. Time-series partitioning and vector search are optional adapters selected by measured need. The schema is divided by domain ownership; no generic JSON document table replaces typed identities, constraints and relationships. JSON fields are permitted for versioned, schema-validated capability payloads where the shape is genuinely extensible.

```text
registry:    agent_definitions, agent_versions, portfolio_profiles,
             portfolio_versions, trading_accounts, portfolio_account_allocations,
             deployments, deployment_epochs, promotion_events
market:      source_contracts, observations, artifact_references
decision:    evaluation_runs, inference_events, decision_events
execution:   signals, execution_events, broker_observations,
             account_reservations, reconciliation_runs
delivery:    outbox_messages, inbox_receipts
```

Foreign keys, uniqueness, effective-interval constraints and explicit state transitions protect referential integrity. Published versions and ledger events are append-only. Mutable projections, schedules and credential references have audit events and concurrency versions. Migrations are reviewed with the domain change that requires them; schema and API contract versions are independent. Backfills preserve original event times and distinguish derived records from source observations.

The outbox guarantees that a committed state transition has a durable delivery intent. Consumers keep inbox receipts and process messages idempotently. The system does not assume exactly-once network delivery. Read models may lag the ledger and expose their observation or projection time. Operational queries that affect capital use current, reconciled account state rather than a stale dashboard projection.

## 7. API and distribution strategy

Expose one logical `/v1` control API for registry commands, lifecycle transitions and queries. Group routes by domain: `agents`, `portfolio-profiles`, `trading-accounts`, `allocations`, `deployments`, `evaluations` and `execution`. Writes require scoped authorization, validation, an idempotency key where retries matter, and optimistic concurrency for updates. Responses include stable IDs, version IDs and lifecycle status. Runtime status streams may use WebSocket or server-sent events; the broker gateway protocol is a separate internal contract.

| Resource | Supported control operations | Removal rule |
| --- | --- | --- |
| Agents | Create draft, publish version, evaluate, approve, activate, pause, retire | Delete only an unreferenced draft; otherwise retire. |
| Portfolio profiles | Create draft, publish version, validate allocations, activate version, retire | Drain dependent deployments and retain referenced versions. |
| Trading accounts | Register, verify, rotate credential reference, activate, suspend, retire | Resolve open work and preserve account/execution history. |
| Allocations | Create, revise capital slice or effective interval, deactivate | Release reservations and preserve prior binding versions. |
| Deployments | Create, validate, activate epoch, pause, switch version, retire | Stop scheduling, reconcile pending work and retain epochs. |

The API returns validation errors with field-level reasons and rejects illegal lifecycle transitions. Authorization scopes separate research edits, live activation, account administration and risk approval. A live deployment change records the actor, approval, effective epoch and configuration hash. Bulk operations use the same per-resource invariants and report individual outcomes; they cannot bypass safety checks.

The control API can run as stateless replicas behind a load balancer. It does not own long-running inference or keep the only copy of configuration in process memory. Workers consume durable work items and load pinned configuration by version. Partition queues by account for execution ordering and by independent workload for ingestion and inference. Use bounded concurrency, leases, backpressure and dead-letter handling with explicit recovery operations.

Start with a modular control application, dedicated worker processes, PostgreSQL outbox/inbox delivery and the C# gateway. Split a module into a separately deployed service only when its ownership and contracts are already stable and an operational requirement justifies the split. A split preserves the same IDs, event schemas and authorization boundaries; it does not create a second source of truth. No broker or agent writes directly into another module's tables.

## 8. Repository and module layout

The following is the **target layout**, not a claim about files already implemented:

```text
documents/
  ARCHITECTURE.md
  decisions/                  # architecture decisions and migrations of intent
src/ledgerquant/
  api/                        # HTTP/stream adapters, request/response schemas
  agents/                     # definitions, capabilities, runner, validation
  portfolios/                 # profile policy and account allocations
  accounts/                   # account registry and broker-state contracts
  deployments/                # epochs, scheduling, activation
  market_data/                # sources, canonicalization, PIT queries
  decisions/                  # context, inference, evaluation, replay
  execution/                  # signals, reservations, dispatch, reconciliation
  messaging/                  # outbox, inbox and delivery adapters
  persistence/                # database setup and module repository adapters
  security/                   # identity, authorization and secret references
  observability/              # metrics, tracing and structured events
  app/                        # dependency assembly and process entry points
gateway/
  LedgerQuant.Execution/      # C# account gateway and broker adapters
migrations/                   # ordered database migrations
tests/
  unit/                       # domain rules
  contract/                   # API, event and adapter contracts
  integration/                # persistence and component boundaries
  end_to_end/                 # signal through reconciliation
```

Within each domain package, separate entities/value objects, application use cases, ports and infrastructure adapters when those layers have real responsibilities. Keep dependencies pointing inward: domain rules know no HTTP framework, database driver or broker SDK. Shared modules contain only cross-cutting primitives with stable meaning; a catch-all `utils` package is not a substitute for domain ownership. Entry points remain thin. A file is split when it contains unrelated responsibilities or becomes hard to review, not to satisfy an arbitrary line count. Scripts are limited to small operational entry points that call tested application services.

Names and paths follow the concepts they implement. Avoid duplicate models for the same fact, copied validation rules, undocumented global state, implicit environment fallbacks and partially wired placeholders. An extension is complete only when persistence, API, lifecycle, authorization, observability and relevant tests agree on its contract. Documentation and migrations change in the same work item as the behavior they describe.

## 9. Engineering and verification gates

- **Domain tests:** lifecycle transitions, profile allocation arithmetic, account-wide limits, version pinning and conflicting edits.
- **Contract tests:** agent capability inputs/outputs, event schemas, API semantics and C# gateway messages; include compatibility and rejection cases.
- **Integration tests:** transactional outbox, inbox deduplication, leasing/fencing, account reservations, migration integrity and secret-reference handling.
- **End-to-end tests:** one observation through `NO_SIGNAL` or a broker rejection/fill to reconciliation, including reconnect, duplicate delivery and process restart.
- **Replay checks:** point-in-time visibility, version identity, recorded-output replay and explicit fresh-inference lineage.
- **Operational checks:** structured reason codes, trace/correlation IDs, queue lag, stale broker observations, reconciliation gaps and fail-closed entry behavior.

Failures are typed and distinguish `NO_SIGNAL` from inference failure, risk rejection from transport failure, and acknowledgement from fill. Required reason codes include source unavailable/stale/schema invalid, context incomplete, inference failed/schema invalid, signal expired, transport unavailable, execution rejected, broker rejected and reconciliation required.

## 10. Implementation sequence

1. Establish domain IDs, typed contracts, migrations and the configuration registry for agents, portfolios, accounts, allocations and deployments.
2. Implement one complete vertical path: canonical observation, point-in-time context, pinned agent version, validated result, append-only decision, account reservation, durable dispatch, C# gateway response and reconciliation.
3. Make that path restart-safe with outbox/inbox idempotency, account serialization, broker-state recovery and contract tests.
4. Add recorded-output replay, evaluation runs and shadow mode using the same domain contracts.
5. Add controlled version promotion and Critic-generated candidates after prospective evaluation and explicit authorization are working.
6. Scale the API and workers independently when measured load or isolation needs require it.

The first release does not need every possible agent capability or a separate service for every module. It does need complete lifecycle and identity handling for each object it exposes. Future adaptability comes from stable contracts, versioned composition and safe deployment transitions, rather than from unbounded configuration or a growing collection of special cases.
