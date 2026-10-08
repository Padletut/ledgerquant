# LedgerQuant Architecture

**Date:** 08.10.2026

**Version:** 2.4.0

**Status:** Target architecture; implementation is not yet present in this repository

## 1. Purpose and design rules

LedgerQuant is an auditable, configurable platform for research, decision support and controlled execution of CFD trading strategies. A Next.js/TypeScript console lets operators inspect the system and manage agents, research, portfolios, accounts and deployments through supported workflows. Every trading decision must retain the exact configuration and information that produced it.

- **Explicit ownership:** agent, portfolio, account, market data, decision and execution concepts have distinct owners and contracts.
- **Single source of truth (SSOT):** versioned configuration and audit history live in the registry and ledger; immutable source artifacts have authoritative references there. Current broker positions, balances and fills come from the broker and are reconciled into the ledger. Search indexes and cached views are rebuildable projections.
- **Reusable behavior:** common lifecycle, validation, persistence and transport behavior is shared through cohesive components. Agent-specific decision logic uses a defined capability interface.
- **Immutable history:** published configuration versions, decision inputs, inference outputs and execution events are never silently rewritten. Changes create new versions or events.
- **Execution safety:** agents propose actions; an account-scoped execution boundary independently enforces broker and capital constraints. The initial boundary is the broker-side execution cBot.
- **Incremental distribution:** components have stable boundaries and can run in separate processes or hosts. Deployment is split where isolation, throughput or availability warrants it.
- **Focused modules:** business rules belong in domain and application modules, adapters handle external systems, and entry points only assemble components.
- **Replaceable integrations:** model providers and broker platforms implement typed ports with verified capabilities. A provider or broker is activated only for the operations its adapter has passed.

Configuration provides adaptability within a supported contract. A new agent using existing capabilities can be registered without source changes. A genuinely new capability, broker protocol or safety rule requires a reviewed implementation, contract tests and deployment. Arbitrary code stored in the database is not an extension mechanism.

## 2. Logical architecture

```text
Broker market feed → Market-data cBot → ingestion adapter → observations
                                                          │
Control API → versioned registry → scheduler               │
                                      │                   │
                                      ▼                   ▼
                            decision workers ← PIT context
                         agents · RAG · memory · replay
                                      │ candidate decision
                                      ▼
                         execution coordinator
                       reservations · account routing
                                      │ authenticated command
                                      ▼
                            execution cBot → Broker
                         risk checks · reconciliation

PostgreSQL: registry, observations, evidence, ledger, outbox and projections
```

The boxes are logical responsibilities, not a requirement for one service per box. The initial deployment may use one control API process, separate workers and two broker-side cBots. The API is one logical, versioned surface and may have multiple stateless replicas. There is no API instance or endpoint set per agent. Workers and cBot connections scale independently, with execution work partitioned by account where ordering or capital safety requires it. The market-data and execution cBots have separate protocols and release lifecycles.

The control plane manages definitions and deployment intent. The data plane ingests observations and builds point-in-time context. The decision plane runs configured agents. The execution plane owns order authorization, dispatch and reconciliation. A research plane reads permitted snapshots and proposes hypotheses; an independent evaluator writes measured evidence, and promotion remains a controlled registry transition. The research plane has no direct path to the broker. A component accesses another component's state through its contract; it does not bypass ownership with ad hoc cross-module database writes.

## 3. Domain model and sources of truth

| Entity | Identity and versioning | Owner and purpose |
| --- | --- | --- |
| `agent_definition` | Stable `agent_id`; immutable `agent_version` | Agent registry. Defines a supported role/capability, input policy, output schema, model and instruction references. |
| `portfolio_profile` | Stable `portfolio_id`; immutable `portfolio_version` | Portfolio registry. Defines investment universe, allocation and risk policy. |
| `trading_account` | Stable `account_id`; operational changes have audit events | Account registry. Identifies broker, adapter, environment, external account key, capabilities and credential reference. |
| `portfolio_account_allocation` | Versioned portfolio/account binding | Portfolio registry. Reserves a capital/risk slice and effective interval. |
| `deployment` | Stable `deployment_id`; immutable `deployment_version` and `epoch_id` | Deployment registry. Binds an agent version to a portfolio version, account allocation, schedule, mode and limits. |
| `broker_feed` | Stable `feed_id`; versioned source and symbol mapping contracts | Market-data owner. Binds a cBot or other broker-data adapter to venue, environment and permitted instruments. |
| `model_profile` | Stable `model_profile_id`; immutable version | Model registry. Binds provider endpoint, model identity, capability snapshot and inference policy. |
| `observation` | Immutable source artifact identity | Market-data owner. Carries source, timing, canonicalization and provenance. |
| `retrieval_snapshot` | Immutable corpus, index and retriever version IDs | Knowledge owner. Identifies the searchable projection used to build context. |
| `episode` | Immutable `episode_id`; summaries have separate versions | Memory owner. Records an eligible, time-scoped experience derived from an audited run. |
| `hypothesis` | Stable `hypothesis_id`; frozen contract version before validation | Research registry. Identifies a Loop A improvement or Loop B payoff discovery and its parent. |
| `evidence_record` | Immutable result ID and evaluation-run reference | Research registry. Stores machine-readable measurements, failure reasons and lineage. |
| `decision` | Immutable `decision_id` and input fingerprint | Decision ledger. Captures the agent result and complete effective configuration. |
| `signal` | Stable `signal_id` | Execution coordinator. Represents one proposed account-scoped trading action. |
| `execution_event` | Immutable event identity | Execution ledger. Records dispatch, execution cBot response, broker events and reconciliation. |

Identifiers are opaque and remain stable across renames. Display names are never routing keys. Every active deployment resolves to one exact agent version, portfolio version, allocation version and account ID before evaluation. These references are copied into decision and signal lineage. A later registry edit cannot change an in-flight decision.

The broker is authoritative for actual orders, fills, positions, balances and margin. LedgerQuant records the last observed broker state with observation time and reconciliation status. Configuration and intended limits are authoritative in the registry; the active execution adapter independently checks live broker state before execution. A market-data feed and a trading account have distinct IDs and are linked explicitly where needed, rather than inferred from a shared broker connection.

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

An agent may emit `NO_SIGNAL`, a typed candidate action or a structured failure. Output validation occurs before signal creation. An Executor is a decision capability. Critic/Research and Discovery are research capabilities: they may propose improvements or new payoff hypotheses, but cannot choose validation results, activate deployments or change capital limits. Additional capabilities use the same lifecycle and typed interfaces; their behavior is not encoded in a growing role-specific switch statement.

### 3.2 Portfolio profiles and account allocations

A portfolio profile is a reusable policy, not a broker account. Its version defines eligible instruments and markets, capital budget, exposure and concentration limits, strategy allocation rules, rebalance or evaluation schedule, and allowed execution modes. Constraints are typed, validated and have explicit units and currencies. Values that affect risk or selection are frozen into the version used by a deployment.

An allocation binds a portfolio profile to a trading account for an effective interval and assigns an explicit capital/risk slice. A profile may span accounts; an account may serve multiple profiles when allocations are compatible. Activation checks that account-wide limits and reserved slices are not exceeded. Runtime risk checks aggregate across all active allocations and deployments on the same account. Where constraints conflict, the stricter applicable limit wins. No agent or profile can loosen an account-level hard limit.

Changing portfolio policy creates a new portfolio version and a controlled deployment transition. Changing the allocation creates a new binding version. Removing an active binding first drains or pauses dependent deployments, resolves pending orders and preserves historical bindings for audit. Renaming a profile does not alter its identity.

### 3.3 Trading accounts

A trading account records broker adapter type, environment, external account key, base currency, allowed instruments, execution capabilities, status and a reference to credentials in a secret store. Raw credentials never enter agent configuration, API responses, audit payloads or source control. Credential rotation changes the reference and records an audit event without changing account identity.

Account states are `DRAFT`, `VERIFIED`, `ACTIVE`, `SUSPENDED` and `RETIRED`. Verification includes broker identity and capability checks. Suspension rejects new entries while preserving broker-side position protection and reconciliation. Retirement requires disabled deployments, no unresolved commands and an explicit position handover policy. Historic accounts and their execution records remain queryable. The same external broker account must not be registered twice in the same environment unless an explicit shared-account policy and serialized execution owner are configured.

### 3.4 Deployments and safe reconfiguration

A deployment binds a published agent version, portfolio version, allocation, account, execution mode (`RESEARCH`, `SHADOW`, `DEMO` or `LIVE`) and schedule. Activation creates an immutable epoch with a content hash of all effective configuration, including prompt, retrieval, memory and model references. Multiple deployments can run concurrently; each result is attributed to its deployment and epoch. A new version becomes effective only at a declared epoch boundary. The scheduler receives a registry change event and periodically reconciles its state against the registry so a missed notification cannot leave it permanently stale.

Before activation, validate schema compatibility, account capability, market permissions, allocation capacity, risk limits, credential availability, retrieval and memory policies, and required approvals. Version transitions are atomic at the deployment level. In-flight evaluations complete under their original epoch; new work uses the new epoch. Conflicting simultaneous changes use optimistic concurrency and return a conflict rather than silently overwriting another operator's edit.

## 4. Decision and execution flow

Source ingestion, decision making and broker execution have separate event histories. An observation is not a signal state, and an execution cBot acknowledgement is not a fill.

```text
Observation → PIT context (RAG + eligible episodes)
                         ↓
               Pinned deployment epoch
                         ↓
                Validated agent result
                ├─ NO_SIGNAL
                ├─ FAILURE
                └─ candidate action
                         ↓
             Account policy and reservation
                         ↓
               Signal and dispatch outbox
                         ↓
              Execution cBot checks live account
                         ↓
               Broker result or uncertainty
                         ↓
                 Reconciliation events
```

Decision events record input observation IDs, retrieved artifact and episode IDs, assembled context hash, agent and portfolio versions, allocation and account IDs, epoch, model and instruction versions, output schema, result, timestamps and reason codes. A candidate action becomes executable only after policy checks, account capacity reservation and durable dispatch intent succeed.

The signal workflow is `CREATED → AUTHORIZED → DISPATCHED → ACKNOWLEDGED → BROKER_ACCEPTED → PARTIALLY_FILLED/FILLED → RECONCILED`, with explicit `REJECTED`, `EXPIRED`, `CANCELLED` and `UNKNOWN_PENDING_RECONCILIATION` paths. Transitions are appended as events; a current-status projection may be updated for queries. A timeout leaves uncertain broker state to reconcile before retrying an order. Every command uses a stable `signal_id` and an idempotency key. Retries must not create a second broker order.

Per-account execution is serialized through one logical owner or an equivalent fenced lease. The coordinator checks aggregate reserved exposure across all deployments on that account, then records the reservation and an outbox message in one database transaction. If the owner changes, fencing prevents the previous owner from dispatching new commands. The execution cBot remains independently capable of rejecting a command based on fresher broker state. Reconciliation releases or adjusts reservations from observed broker outcomes.

### 4.1 Execution cBot wire contract and connection safety

The authenticated, versioned execution protocol uses a routing envelope with `protocol_version`, `message_type`, `message_id`, `correlation_id`, `account_id`, `created_at` and `expires_at`. A trading command also carries `signal_id`, `deployment_id`, `epoch_id`, agent and portfolio version IDs, instrument, side, order semantics and applicable risk-policy reference. Optional agent output fields are part of the agent schema, not universal protocol fields.

Delivery may be duplicated, delayed or reordered. The execution cBot persists command idempotency and reports acknowledgements separately from broker acceptance and fills. Expired commands cannot be executed after reconnect. After a connectivity failure threshold, new entries stop, pending commands are invalidated or reconciled, and existing protective orders remain under cBot and broker control. Reconnection requires account and order reconciliation before new entries resume.

Transport uses TLS, scoped and revocable credentials, rotation, rate limits and connection audit. The execution cBot receives only the account-scoped commands it is authorized to execute. The control API cannot bypass its risk checks.

### 4.2 Market-data cBot ingestion contract

The separate market-data cBot reads broker market events and publishes versioned observations to an authenticated ingestion adapter. Its envelope includes protocol version, message ID, feed ID and send time. The payload covers instrument identity, broker symbol, quote/bar/event type, bid/ask or other applicable values, broker event timestamp, cBot observation timestamp, source sequence, cBot build version and symbol-map version. If the broker supplies no sequence, the cBot emits a boot/session ID and monotonic local sequence; repeated equal prices are not deduplicated solely by content hash. The ingestion adapter records its receive and commit times, validates units and schema, and assigns canonical observation IDs. A feed is registered with an explicit source contract before it can supply Executor context.

The market-data cBot has no order command handler, execution credentials or route to the execution coordinator. It is deployed and monitored independently from the execution cBot. Authentication scopes allow publishing observations only for its registered feed. Where the broker platform cannot provide physically separate privileges, the code and inbound protocol still expose no trading operation; contract tests verify this boundary.

The stream tolerates reconnects, duplicate messages and out-of-order delivery. Sequence gaps, clock skew, stale feeds and dropped events are observable states. Backpressure uses bounded buffering and an explicit gap/recovery record; it must not silently label a delayed quote as current. A required stale feed prevents new decisions that depend on it, while the execution cBot continues broker-side position protection. Live executable quote and account checks remain with the execution cBot, because the ingested data may be delayed.

### 4.3 Adapting the existing execution cBot

The execution cBot is planned to be brought from another project and adapted to LedgerQuant's account-scoped command, acknowledgement, risk and reconciliation contracts. It is not yet code in this repository. Integration starts by identifying its existing order and position-management behavior, then mapping those behaviors to the versioned wire contract and LedgerQuant IDs. Preserve broker-side protective behavior during adaptation; any changed safety rule requires a specific test and review. The imported cBot must reject unknown protocol versions, stale epochs, duplicate signals and commands for another account. Its broker events are mapped to immutable execution events without assuming that a local acknowledgement proves a broker fill.

### 4.4 Broker adapter ports and capability gates

Broker connectivity is split into typed ports for market data, account state and execution. An adapter may implement one or several ports. The target adapter families are broker APIs, cBots, MT4, MT5 and NinjaTrader; each is a distinct integration with its own deployment and protocol constraints. The cBots are the initial adapters. A platform name in the registry does not imply that all operations are implemented or safe for live use.

Every adapter publishes a versioned capability snapshot: supported instruments and order types, market-data modes, account and position queries, cancel/modify behavior, protective orders, partial fills, timestamp quality, precision, rate limits, idempotency mechanism and reconciliation coverage. Account and feed activation check the required capabilities against the deployment contract. Unsupported operations fail validation before a signal is sent. Broker-specific symbols, volume units, currencies, time zones and order states are normalized at the adapter boundary while original broker identifiers and payload references remain in the ledger.

Exactly one logical execution owner is assigned per trading account across all adapter types. Each execution adapter maps the stable `signal_id` to broker order IDs, enforces expiry and duplicate protection, checks current account and quote state, and emits acknowledgements, rejections, fills and reconciliation events through the common contract. If a platform cannot provide an independent broker-side cBot, its connector includes an isolated account-scoped safety component with the same authority to reject and manage protective orders. A new adapter reaches `LIVE` eligibility only after contract, failure-recovery, reconciliation and broker-specific safety checks pass in demo or shadow mode.

Model providers and broker adapters are different extension points. Changing a model cannot change broker safety behavior; changing a broker adapter cannot change the frozen decision or payoff contract. Both changes produce versioned deployment lineage and targeted regression evaluations.

## 5. Data lineage and replay

Each external artifact is normalized by a source-specific, versioned canonicalizer before its content hash is calculated. Preserve the original payload or an immutable reference where legally and operationally possible. Canonicalization records what was normalized; it cannot discard fields merely because they appear irrelevant.

An observation records `source_id`, `source_type`, `source_event_time`, `observed_at`, `received_at`, `ingested_at`, `available_at`, `canonicalizer_version`, `content_sha256` and `raw_artifact_reference`. Broker-feed observations also record feed ID, cBot version, symbol-map version and source sequence/message ID. The source contract defines `available_at`, which controls point-in-time visibility. For a broker cBot feed, it cannot precede validated durable ingestion: a broker timestamp or cBot clock does not make delayed data available earlier. Replay at time `T` may read only records whose declared `available_at ≤ T` and whose source revisions were visible then. Clock skew and transport delay are measured separately.

An inference fingerprint binds the visible context, canonicalization version, agent and portfolio versions, retrieval and memory policy versions, selected artifact and episode IDs, model/provider, instructions, tools, output schema and inference parameters. Recorded-output replay returns the persisted result for that exact contract. Fresh-inference replay invokes the model again and stores a distinct event; probabilistic inference may differ. Replay results state the mode and the source-availability contract.

Point-in-time filtering alone does not eliminate survivorship bias, missing historical observations, changed providers or execution-model differences. Evaluation reports identify these limits and keep research, shadow, demo and live results separate.

### 5.1 Retrieval-augmented generation (RAG)

Retrieval has two separate logical domains with distinct corpora, policies, indexes and permissions. They may share storage technology, but never an unrestricted `vector_db_of_everything` or a query that silently mixes purposes:

| Domain | Consumer | Permitted content and authority |
| --- | --- | --- |
| **Market knowledge RAG** | Executor at decision time | News, macro releases, central-bank communication, broker observations and event metadata available at that instant. The source artifact and its `available_at` govern visibility. |
| **Research knowledge RAG** | Critic/Research and Discovery | Research literature, methods, approved analyses and narrative reports for idea generation and explanation. Retrieved prose is background material; structured evaluation results come from the evidence registry. |

Each domain builds searchable, versioned projections from approved source artifacts. Each document and chunk retains its source reference, content hash, source event time when defined, `available_at`, canonicalizer and chunker versions. Embeddings, lexical indexes and ranking scores are derived data; the source artifact remains authoritative. Reindexing creates a new index version and does not rewrite earlier retrieval records. Research material is not automatically eligible for Executor context; moving content between domains requires source review, policy approval and a new version.

High-frequency broker quotes, ticks and bars from the market-data cBot are primarily structured time-series observations queried by instrument and time. They do not need to become vector documents. Market knowledge RAG may retrieve associated broker notices or event metadata, while structured market queries supply prices and feed-health facts under the same point-in-time rules.

An agent version pins a retrieval policy: domain, allowed corpora and source types, account/portfolio scope, index and embedding versions, retriever/ranker version, point-in-time filters, freshness limits, relevance threshold and context budget. Market retrieval applies authorization and `available_at` filtering **before** ranking. Research retrieval also records the information cutoff used for each study. Hybrid lexical/vector retrieval is permitted behind one typed interface; changing the search implementation must preserve the retrieval contract and create a new version where results can differ.

Each decision or research run records the query hash, retrieval domain and snapshot, selected chunk IDs and order, content hashes, scores, source citations, filters and exact assembled context hash. Recorded-output replay uses this captured context; a new retrieval is a separate run. Mandatory market evidence that is absent, stale or outside scope produces `CONTEXT_INCOMPLETE` or `SOURCE_STALE`, never invented context. Retrieved text is untrusted data: it cannot change system instructions, call tools, redefine success metrics or override execution policy. Source and account access rules apply before content reaches the model.

### 5.2 Episodic memory

Episodic memory stores selected, auditable experiences from prior runs: the decision, cited evidence, subsequent execution outcome, reconciliation status and lessons or summaries derived from those records. The immutable episode references its original event IDs. Model-written summaries are separate, versioned derivatives with their own `available_at`, authoring model/instruction identity, validation status and source references. A memory writer records an episode only after its required outcome is observed and reconciled; it does not turn an unverified model assertion into a fact.

Every episode has an `available_at` no earlier than the time it was actually written and all evidence and outcomes used to form it. Memory retrieval respects that timestamp during replay, plus environment, agent, portfolio and account permissions. Cross-account or research-to-live reuse requires an explicit policy. Selection has relevance, quality, deduplication, retention and context-budget rules; the selected episode IDs, order and content hashes are recorded with the decision. Retiring or correcting a memory adds a new status event; the original evidence remains auditable. Summaries are regenerated from source episodes when their contract changes.

Memory may inform a decision but cannot activate an agent, modify risk limits or issue an order. A missing memory store follows the deployment's declared degradation policy: use the permitted empty-memory path or stop evaluation. The choice and reason are recorded. Outcome data from after a historical decision cannot appear in that decision's replay context.

### 5.3 Versioned evaluations

An evaluation suite fixes dataset and source snapshots, temporal splits, expected labels where available, scoring rules, baseline, minimum gates and evaluation code version. Development data is separate from a frozen holdout. Walk-forward windows and prospective shadow runs are used for trading behavior; repeated prompt changes are not tuned against the holdout. A changed suite or threshold creates a new suite version rather than rewriting an old result; it cannot reclassify a failed frozen hypothesis without a new child hypothesis and untouched validation evidence.

Evaluate the complete decision contract, including retrieval, memory, prompt, model and policy versions. Gates cover retrieval relevance and evidence coverage, citation faithfulness, temporal leakage, schema validity, justified abstention, unsafe actions, capital-limit violations, latency and cost. Trading metrics use the same market window and execution assumptions for candidate and baseline, report sample sizes and uncertainty, and keep simulated outcomes distinct from broker-observed outcomes. A passing offline score does not authorize live trading.

Every run stores candidate and baseline IDs, suite version, case IDs, inputs, outputs, metric definitions, failures and reproducibility metadata. Research promotion decisions cite both the evaluation run and its structured evidence record, plus any accepted exceptions. Evals are also regression gates for adapter, index, model and memory-policy changes, not only prompt changes. After activation, ongoing evaluation watches data quality, behavior and risk drift; a breached hard gate pauses new entries or rolls back through the deployment workflow.

### 5.4 Prompt optimization and promotion

Prompts are immutable, versioned artifacts referenced by agent versions. An optimizer or Critic may propose prompt candidates using only its permitted development evidence and a bounded experiment budget. Each experiment links to a Loop A hypothesis and research trial; it records the proposal method, parent prompt, candidate hash, retrieval/memory/model configuration and evaluation suite. The independent evaluator writes measured results to the evidence registry. Candidates are compared with the active baseline under the same conditions; changing multiple components is either isolated in separate experiments or identified as a combined change.

The optimizer cannot read the frozen holdout while generating candidates, promote its own result, change account policy or edit active versions. Candidate selection passes contract checks, temporal evaluation, stress cases and prospective shadow evidence before explicit approval. Activation creates a new deployment epoch; rollback selects a prior approved version and records a new epoch. Prompt text alone is never treated as the complete unit of optimization because retrieved context, memory and model behavior also affect the result.

## 6. Two self-improvement loops and structured evidence

The research system has two explicit loops. Both create hypotheses and evidence; neither directly changes a live deployment.

| Loop | Research question | Contract boundary |
| --- | --- | --- |
| **A — improve an existing decision system** | Can a prompt, model, feature, retrieval, memory or decision-rule change improve the current Executor? | The decision target and payoff contract stay fixed. Compare a candidate with the current baseline under the same evaluation and cost assumptions. |
| **B — discover a new payoff contract** | Is there another decision and payoff for which observable information has stable economic value? | Register new decision, feature, payoff and cost contracts before validation. A changed payoff is a new hypothesis, even if it reuses an existing agent. |

The common research path is `PROPOSE → FREEZE CONTRACT → DEVELOP → INDEPENDENT TEMPORAL VALIDATION → COST/STRESS VALIDATION → PROSPECTIVE SHADOW → APPROVAL`. A Critic or Discovery agent can submit candidates and inspect permitted evidence, but the evaluation service computes outcomes and the promotion authority controls status. Loop B may produce a new agent capability, portfolio policy or execution mode; such changes follow the normal code and risk review before deployment.

### 6.1 Ex-ante hypothesis contracts

Each hypothesis receives a stable `hypothesis_id`, optional `parent_hypothesis_id`, loop type and immutable contract hash before it can enter validation. Its contracts specify:

- `decision_contract`: eligible instruments, decision time, action space, entry/exit rules, holding horizon and baseline;
- `feature_contract`: source IDs, transformations, publication delays, `available_at` semantics and missing-data behavior;
- `payoff_contract`: outcome calculation, settlement horizon, units, success metrics, risk metrics, minimum gates and comparator;
- `cost_contract`: spread, commissions, financing, slippage, rejection and fill assumptions, with their source and version;
- `development_window` and `validation_windows`: fixed temporal boundaries, instrument scope, data snapshots, evaluation suite and minimum sample size;
- research family and trial budget: all related searches and attempts counted for multiple-testing review.

Contracts are registered and frozen before the independent evaluator exposes validation outcomes. The proposer cannot edit the payoff definition, metric, threshold or validation window after seeing those outcomes. Any changed definition becomes a child hypothesis with a new ID and a new untouched validation plan. Related child attempts stay in one research family; exhausted holdout windows cannot be reused as fresh evidence. Loop A preserves the parent's payoff contract; a payoff change is routed to Loop B.

### 6.2 Structured evidence registry

The evidence registry stores typed, queryable facts rather than treating a narrative report or embedding as the result. A complete hypothesis view exposes at least:

```text
hypothesis_id
parent_hypothesis_id
loop_type
decision_contract
feature_contract
payoff_contract
cost_contract
development_window
validation_windows
pair_breadth
temporal_breadth
net_expectancy
drawdown
calibration
failure_reason
status
```

Fields through `validation_windows` are frozen proposal metadata. Breadth and performance fields are computed per evaluation run, with units, sample counts, uncertainty, market window, data and code versions, baseline, cost assumptions and provenance. `pair_breadth` counts covered instrument pairs under the registered universe; `temporal_breadth` records independent windows or regimes that passed. `failure_reason` is typed, so transport failure, insufficient data, temporal instability and cost failure remain distinguishable. A current hypothesis view joins immutable contracts, append-only result records and status events; no agent edits measured fields.

```text
PROPOSED → DEVELOPMENT_SURVIVOR → SHADOW_ELIGIBLE → PROSPECTIVE → PROMOTED
       └→ REJECTED            ├→ TEMPORAL_FAILED
                             └→ COST_FAILED
```

Status transitions are validated against required evidence and written as events with actor, time, rule version and evaluation references. A `DEVELOPMENT_SURVIVOR` is only a candidate for independent validation. `SHADOW_ELIGIBLE` requires temporal and cost gates. `PROMOTED` requires prospective evidence and explicit approval; promotion then creates a new versioned deployment epoch. Failed or abandoned trials remain visible, including child and sibling hypotheses, to prevent selective reporting.

### 6.3 Separation of discovery, explanation and judgment

Research knowledge RAG helps agents find methods and explain reports. The structured evidence registry is authoritative for hypothesis contracts, measured results and status. An agent may cite a report, but a claim that a payoff survived validation must resolve to evidence records and the evaluator's gate decision. Access to frozen holdout outcomes is reserved for the independent evaluator and reviewers after candidate selection. Research agents see development evidence and only released validation summaries; they cannot choose a new success definition in response to a failed validation.

Evaluation reports show the number of related trials, all preregistered windows, results by pair and period, net costs, drawdown, calibration, uncertainty and failure reasons. A promising isolated backtest is insufficient for `SHADOW_ELIGIBLE`. Prospective evidence is collected after registration under the same decision and payoff definitions. Any exceptional override is recorded with its reason and approver; it does not rewrite the original result.

## 7. Persistence and consistency

PostgreSQL is the initial durable store. Time-series partitioning and a vector index are optional adapters selected by measured need. The schema is divided by domain ownership; no generic JSON document table replaces typed identities, constraints and relationships. JSON fields are permitted for versioned, schema-validated capability payloads where the shape is genuinely extensible.

```text
registry:    agent_definitions, agent_versions, prompt_versions,
             model_providers, model_profiles, model_profile_versions,
             provider_capability_snapshots,
             broker_connections, broker_capability_snapshots,
             retrieval_policies, memory_policies, portfolio_profiles,
             portfolio_versions, trading_accounts, portfolio_account_allocations,
             deployments, deployment_epochs, promotion_events
market:      broker_feeds, source_contracts, observations, artifact_references
knowledge:   corpora, document_chunks, index_versions,
             retrieval_snapshots, retrieval_events
memory:      episodes, episode_events, summary_versions, memory_retrieval_events
decision:    inference_events, decision_events
evaluation:  evaluation_suites, evaluation_runs, evaluation_case_results,
             optimization_experiments
research:    hypotheses, hypothesis_contracts, research_trials,
             evidence_records, hypothesis_status_events
execution:   signals, execution_events, broker_observations,
             account_reservations, reconciliation_runs
delivery:    outbox_messages, inbox_receipts
```

Foreign keys, uniqueness, effective-interval constraints and explicit state transitions protect referential integrity. Published versions, frozen hypothesis contracts and ledger events are append-only. Mutable projections, schedules and credential references have audit events and concurrency versions. Migrations are reviewed with the domain change that requires them; schema and API contract versions are independent. Backfills preserve original event times and distinguish derived records from source observations.

The outbox guarantees that a committed state transition has a durable delivery intent. Consumers keep inbox receipts and process messages idempotently. The system does not assume exactly-once network delivery. Search indexes, memory summaries and read models may lag their source records; each exposes its source version and projection time. Operational queries that affect capital use current, reconciled account state rather than a stale dashboard projection.

## 8. Model provider architecture

Agents use a typed model-provider port; provider SDKs and HTTP formats stay inside adapters. The initial target adapters are OpenAI, Claude, Ollama, LM Studio and a local `llama.cpp` server. Llama is a model family rather than a transport: Llama-family models are selected through a verified local runtime such as Ollama, LM Studio or `llama.cpp`. Additional providers use the same registration and conformance process.

A versioned model profile fixes provider instance, endpoint identity, model ID and revision or local artifact digest, inference parameters, credential reference, allowed tools, output schema and resource limits. The provider capability snapshot records supported structured output, tool calls, streaming, embeddings, context limits and usage reporting. Text generation and embeddings are separate ports; a generation model is not assumed to supply embeddings. A published agent version binds one exact model-profile version and the deployment validates every required capability before activation.

The adapter normalizes completed output, refusal or incomplete result, tool requests, usage, latency, provider request ID and error type. The domain validates the normalized result against the agent schema regardless of provider claims. OpenAI-compatible local endpoints are treated as transport options, not proof of identical tools, schema enforcement or token accounting. Each endpoint and model combination must pass conformance tests for the capabilities it advertises. Provider outages, rate limits and malformed output remain distinct failure reasons.

Cloud credentials live in the secret store; local endpoints are explicitly registered and access-controlled. Operators choose which data classes may leave the local system for each provider. Neither browser code nor agent configuration contains raw API keys. A live deployment never silently switches provider or model after a failure: fallback requires a preapproved versioned policy and evaluation evidence, and every invocation records the provider, model revision, profile version and effective prompt/context fingerprint. Local model upgrades or changed weights create a new model-profile version.

## 9. API and distribution strategy

Expose one logical `/v1` control API for registry commands, lifecycle transitions and queries. Group routes by domain: `agents`, `model-providers`, `portfolio-profiles`, `trading-accounts`, `broker-connections`, `allocations`, `broker-feeds`, `deployments`, `knowledge`, `memory`, `hypotheses`, `evidence`, `evaluations`, `optimization` and `execution`. Writes require scoped authorization, validation, an idempotency key where retries matter, and optimistic concurrency for updates. Responses include stable IDs, version IDs and lifecycle status. Runtime status streams may use WebSocket or server-sent events; broker ingestion and execution transports are separate internal contracts.

| Resource | Supported control operations | Removal rule |
| --- | --- | --- |
| Agents | Create draft, publish version, evaluate, approve, activate, pause, retire | Delete only an unreferenced draft; otherwise retire. |
| Portfolio profiles | Create draft, publish version, validate allocations, activate version, retire | Drain dependent deployments and retain referenced versions. |
| Trading accounts | Register, verify, rotate credential reference, activate, suspend, retire | Resolve open work and preserve account/execution history. |
| Broker feeds | Register source and symbol map, verify adapter, activate, suspend, retire | Preserve observation lineage and feed-health history. |
| Model providers and broker connections | Register endpoint/adapter, verify capabilities, rotate credential reference, suspend | Preserve invocation and broker event lineage; never expose secrets. |
| Allocations | Create, revise capital slice or effective interval, deactivate | Release reservations and preserve prior binding versions. |
| Deployments | Create, validate, activate epoch, pause, switch version, retire | Stop scheduling, reconcile pending work and retain epochs. |
| Knowledge and memory policies | Register corpus, index and policy versions; inspect retrieval and episodes | Retire projections or policies while preserving referenced source and decision lineage. |
| Evaluation and optimization | Publish suites, run evaluations, propose and review prompt candidates | Keep immutable experiment and promotion history. |
| Hypotheses and evidence | Register/freeze contracts, query trials and evidence, request independent evaluation, review status | Preserve failed trials and contracts; corrections create new records or child hypotheses. |

The API returns validation errors with field-level reasons and rejects illegal lifecycle transitions. Authorization scopes separate research proposals, evaluation-result writes, live activation, account administration and risk approval. Research agents have no write access to computed evidence or status gates. A live deployment change records the actor, approval, effective epoch and configuration hash. Bulk operations use the same per-resource invariants and report individual outcomes; they cannot bypass safety checks.

The control API can run as stateless replicas behind a load balancer. It does not own long-running inference or keep the only copy of configuration in process memory. Workers consume durable work items and load pinned configuration by version. Partition queues by account for execution ordering and by independent workload for ingestion and inference. Use bounded concurrency, leases, backpressure and dead-letter handling with explicit recovery operations.

Start with a modular control application, dedicated worker processes, PostgreSQL outbox/inbox delivery and the two cBots. Split a module into a separately deployed service only when its ownership and contracts are already stable and an operational requirement justifies the split. A split preserves the same IDs, event schemas and authorization boundaries; it does not create a second source of truth. No broker adapter or agent writes directly into another module's tables.

## 10. Operator console (Next.js + TypeScript)

The frontend is a real operational console, not a separate decision engine. Use Next.js App Router and TypeScript with route files kept thin, domain-owned screens and components, and a typed client generated from the control API contract. Server-rendered reads provide the initial view; interactive components handle filters, forms, charts and live status. The frontend calls the control API and its authorized event stream. It never reads PostgreSQL directly, contacts a broker or model provider, or computes authoritative risk and evaluation status in the browser.

| Area | Required views and actions |
| --- | --- |
| **Overview** | System health, active deployments, account equity and exposure, recent decisions, alerts and reconciliation backlog. Each card shows source and freshness. |
| **Agents** | Executor, Critic and Research/Discovery agents; versions, instructions, provider/model profiles, allowed tools, confidence calibration, lifecycle and promotion evidence. Register and verify model endpoints; create and compare drafts without changing active epochs. |
| **Research** | Hypotheses, experiments, candidates, temporal validation, pair and period breadth, cost stress, rejected and null results. Show frozen contracts, parent lineage, trial family and typed failure reasons. |
| **Evaluations** | Agent-version comparisons, payoff, drawdown and tails, calibration, temporal transport and prospective evidence. Show baseline, sample size, uncertainty, cost assumptions and mode beside each result. |
| **Portfolios** | Profiles, risk policies, allocations and aggregate exposure by profile and account. Show effective versions and breached limits. |
| **Accounts** | Demo and live accounts, broker connections and capabilities, equity, margin, positions, pending orders and reconciliation. Display adapter identity, last broker observation and unresolved discrepancies. |
| **Deployments** | Research, shadow, demo and live deployments; epochs, pinned versions and promote, pause or retire workflows. Show approvals and the exact configuration that will become active. |
| **Market Data** | Feed registration and health, historical coverage, symbol maps, gaps, stale observations and source provenance. Distinguish event time from system availability time. |
| **Execution** | Signals, risk and broker rejections, fills, latency and execution cBot or other adapter status. Link each event to account, deployment, decision and reconciliation state. |

Navigation and detail pages use stable IDs and cross-links so an operator can trace an alert to its feed, decision, signal, broker event and deployed versions. Global filters include environment, account, portfolio, agent, broker adapter, instrument and time window. Live, demo, shadow and research modes are visually distinct on every action and result. Prices, units, currencies, time zones and data age are explicit. Missing data renders an honest empty, stale or unavailable state rather than a fabricated zero or example row.

The control API remains the authorization and validation authority. The web server manages the user session and forwards scoped requests; browser code receives only permitted data and never credentials. Route access and backend permissions are checked separately. Promotion and live account changes use a review screen that shows diff, evidence, effective epoch and approver before the final command. Optimistic-concurrency conflicts, pending approvals and reconciliation uncertainty are shown as first-class states. A click acknowledgement is not displayed as a broker fill.

Read models support pagination, filtering and stable sorting. Live updates carry event IDs and observation times; the client reconnects by cursor and refetches authoritative state after a gap. Charts and tables have accessible text alternatives and responsive layouts. Frontend work is shipped by complete vertical screen flows tied to real API contracts; navigation entries become available when their data and actions are implemented, without mock operational metrics in production.

## 11. Repository and module layout

The following is the **target layout**, not a claim about files already implemented:

```text
documents/
  ARCHITECTURE.md
  decisions/                  # architecture decisions and migrations of intent
contracts/                    # OpenAPI, events and broker wire schemas
src/ledgerquant/
  api/                        # HTTP/stream adapters, request/response schemas
  agents/                     # definitions, capabilities, runner, validation
  models/                     # model profiles, provider and embedding ports
  brokers/                    # adapter ports, capabilities and connection registry
  portfolios/                 # profile policy and account allocations
  accounts/                   # account registry and broker-state contracts
  deployments/                # epochs, scheduling, activation
  market_data/                # sources, canonicalization, PIT queries
  knowledge/                  # RAG corpora, indexes, retrieval, citations
  memory/                     # episodes, summaries, selection policy
  decisions/                  # context assembly, inference, replay
  evaluations/                # suites, cases, metrics, comparisons
  optimization/               # prompt candidates and experiment workflow
  research/                   # hypotheses, payoff discovery, evidence registry
  execution/                  # signals, reservations, dispatch, reconciliation
  integrations/
    llm/                      # OpenAI, Claude and local runtime adapters
    broker/                   # API, cBot, MT4, MT5, NinjaTrader adapters
  messaging/                  # outbox, inbox and delivery adapters
  persistence/                # database setup and module repository adapters
  security/                   # identity, authorization and secret references
  observability/              # metrics, tracing and structured events
  app/                        # dependency assembly and process entry points
apps/web/
  src/app/(console)/
    overview/                  # system health and alert summary
    agents/                    # agent registry and versions
    research/                  # hypotheses and trials
    evaluations/               # comparisons and evidence
    portfolios/                # profiles, policies and exposure
    accounts/                  # account and broker state
    deployments/               # epochs and promotion workflow
    market-data/               # feeds, coverage and provenance
    execution/                 # signals and broker outcomes
  src/features/                # domain screens, forms, charts and tables
  src/components/              # shared accessible UI primitives
  src/lib/api/                 # generated control-API client and query helpers
  src/lib/auth/                # session and authorization presentation
  src/lib/streams/             # event cursor and reconnect handling
cbots/
  LedgerQuant.Execution/      # adapted C# execution cBot
  LedgerQuant.MarketData/     # broker market-data publishing cBot
migrations/                   # ordered database migrations
tests/
  unit/                       # domain rules
  contract/                   # API, event and adapter contracts
  integration/                # persistence and component boundaries
  end_to_end/                 # signal through reconciliation
```

Within each domain package, separate entities/value objects, application use cases, ports and infrastructure adapters when those layers have real responsibilities. Keep dependencies pointing inward: domain rules know no HTTP framework, database driver or broker SDK. Shared modules contain only cross-cutting primitives with stable meaning; a catch-all `utils` package is not a substitute for domain ownership. Entry points remain thin. A file is split when it contains unrelated responsibilities or becomes hard to review, not to satisfy an arbitrary line count. Scripts are limited to small operational entry points that call tested application services.

Names and paths follow the concepts they implement. Avoid duplicate models for the same fact, copied validation rules, undocumented global state, implicit environment fallbacks and partially wired placeholders. An extension is complete only when persistence, API, lifecycle, authorization, observability and relevant tests agree on its contract. Documentation and migrations change in the same work item as the behavior they describe.

## 12. Engineering and verification gates

- **Domain tests:** lifecycle transitions, profile allocation arithmetic, account-wide limits, version pinning and conflicting edits.
- **Contract tests:** agent capability inputs/outputs, event schemas, API semantics and both cBot protocols; include compatibility, authorization and rejection cases.
- **Integration tests:** transactional outbox, inbox deduplication, leasing/fencing, account reservations, migration integrity and secret-reference handling.
- **End-to-end tests:** one observation through `NO_SIGNAL` or a broker rejection/fill to reconciliation, including reconnect, duplicate delivery and process restart.
- **Replay checks:** point-in-time visibility, version identity, recorded-output replay and explicit fresh-inference lineage.
- **RAG and memory checks:** source authorization, retrieval provenance, stale or missing evidence, prompt-injection isolation, episode eligibility and no future-outcome leakage.
- **Broker-feed checks:** source and symbol identity, event/receive/availability times, duplicate and reordered events, reconnect gaps, backpressure and stale-feed handling; verify the market-data cBot has no execution path.
- **Execution cBot checks:** account routing, duplicate and expired commands, independent risk rejection, broker acknowledgement versus fill, protective positions and reconnect reconciliation.
- **Provider checks:** schema and tool capability conformance, refusal and error normalization, local artifact pinning, secret isolation and no unapproved live fallback.
- **Broker-adapter checks:** platform-specific symbol/volume mapping, account ownership, order lifecycle, protective orders, reconnect and reconciliation before live eligibility.
- **Frontend checks:** typed API contract, permission and mode visibility, promotion review, stale/empty/error states, stream-gap recovery and no secrets or fabricated metrics in browser output.
- **Evaluation checks:** frozen holdout access, suite versioning, baseline comparability, regression gates and experiment reproducibility.
- **Discovery checks:** contract freeze before validation, immutable trial lineage, derived metric ownership, multiple-testing accounting, pair/time breadth and enforced status transitions.
- **Operational checks:** structured reason codes, trace/correlation IDs, queue lag, stale broker observations, reconciliation gaps and fail-closed entry behavior.

Failures are typed and distinguish `NO_SIGNAL` from inference failure, risk rejection from transport failure, and acknowledgement from fill. Required reason codes include source unavailable/stale/schema invalid, context incomplete, inference failed/schema invalid, signal expired, transport unavailable, execution rejected, broker rejected and reconciliation required.

## 13. Implementation sequence

1. Establish domain IDs, typed API/wire contracts, migrations, provider and broker ports, and registries for agents, model profiles, portfolios, accounts, feeds, allocations and deployments.
2. Build the Next.js/TypeScript console shell with authentication, typed API client and the first real overview/account/feed status flows as their read models become available.
3. Bring in the existing execution cBot and adapt its account routing, idempotency, risk checks, event reporting and reconciliation to the new contracts.
4. Build the separate market-data cBot and ingestion path with source identity, symbol mapping, canonical observations, feed-health reporting and point-in-time visibility.
5. Complete one vertical path with a conformance-tested model provider: broker observation, pinned agent and model-profile versions, validated decision, account reservation, durable dispatch, execution cBot response and broker reconciliation. Show that path and its failures in the console.
6. Make that path restart-safe with outbox/inbox idempotency, account serialization, feed-gap recovery, broker-state recovery and contract tests.
7. Add recorded-output replay and versioned evaluation suites; deliver Agents, Evaluations, Deployments and Execution screens against real query and command contracts.
8. Add source-backed RAG and episodic memory with point-in-time replay checks, then Research, Portfolios and Market Data screens as their contracts are complete.
9. Add the structured hypothesis/evidence registry and independent temporal, cost and breadth evaluations before automating research proposals.
10. Add shadow mode, prospective evaluation and controlled promotion; introduce Loop A Critic/optimizer candidates and Loop B Discovery candidates only after these gates work.
11. Complete the remaining conformance-tested OpenAI, Claude, Ollama, LM Studio and local Llama-runtime adapters, plus broker API, MT4, MT5 and NinjaTrader integrations as each reaches its required capability gate.
12. Scale the API, frontend and workers independently when measured load or isolation needs require it.

The first release does not need every possible agent capability or a separate service for every module. It does need complete lifecycle and identity handling for each object it exposes. Future adaptability comes from stable contracts, versioned composition and safe deployment transitions, rather than from unbounded configuration or a growing collection of special cases.
