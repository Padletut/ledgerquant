LedgerQuant Architecture Specification Manual
System Blueprint & Design Framework
Version: 1.0.0 (Alembic Baseline Ready)
Classification: Proprietary Quantitative Infrastructure


Executive Architectural Summary
LedgerQuant is an isolated, adaptive, multi-agent feature generation and sentiment synthesis factory designed specifically for Contract for Difference (CFD) algorithmic trading.
Unlike systems built on hardcoded conditional loops or static neural boundaries, LedgerQuant treats agent roles, instruction sets, data contracts, and optimization heuristics as dynamic database configurations. The runtime codebase acts as a lean, stateless, polymorphic runner.
By enforcing absolute structural decoupling, the platform satisfies four core design principles:
• Single Source of Truth (SSOT): All execution states, prompt versions, schema validations, and incoming data artifacts are anchored in an append-only PostgreSQL ledger.
• Don't Repeat Yourself (DRY): A unified, generalized executor runner handles all agent lifecycles, streaming interfaces, error isolation layers, and inference routines.
• Lookahead Isolation: Rigorous Point-in-Time (PIT) validation barriers blind the probabilistic layers to future data points during backtests, ensuring perfect historical simulation validity.
• Runtime Adaptability: Asymmetric Evolutionary Critic loops optimize systemic instructions and risk parameters directly inside the database registry, allowing the network to adapt without requiring code rewrites, redeployments, or service restarts.


1. High-Level System Topology & State Machine
To ensure maximum isolation, operational resilience, and capital protection, LedgerQuant enforces strict network and execution boundaries between three micro-environments:
unset
[ LEDGERQUANT SYSTEM NETWORK BOUNDARY (Docker) ] +---------------------------------------------------------------------------------------+ | | | [ Ext. Ingestion Workers ] ──> [ TimescaleDB / PGVector ] <── [ FastAPI Gateway ] | | │ ▲ | | ▼ │ | | [ Adaptive Runner ] ──────────────────┘ | | | +---------------------------------------------------------------------------------------+ │ (Secure WS Channel / TLS) │ ▼ [ External C# cBot ] (6k LOC Safety Gateway)

1.1 The Lifecycle of a Trading Signal
Every calculated signal traverses a strict, unidirectional state machine to guarantee absolute traceability across both live and backtesting environments:
unset
[ UNSTRUCTURED TEXT ] │ ▼ ( INGESTED ) ──> Raw text hashed (SHA-256) and timestamped (T_ingest) in Raw Web Sink. │ ▼ ( EVALUATING ) ──> Adaptive Runner compiles context using isolated Point-in-Time rules. │ ▼ ( BROADCASTED ) ──> Validated JSON schema assigned a UUID, logged to audit, and pushed to WS. │ ▼ ( ACKNOWLEDGED ) ──> External C# cBot parses payload and verifies internal risk tolerances. │ ▼ ( EXECUTED/REJECTED )──> cBot closes loop via inbound WS report, updating the original audit row.

───

2. Data Lineage & Determinism Strategy
Because Large Language Models (LLMs) operate probabilistically due to hardware-level floating-point non-associativity and asynchronous GPU thread scheduling, determinism must be strictly enforced at the database boundaries of the framework.
2.1 The Hash-and-Lock Gateway
Every external data artifact processed by ingestion tasks must undergo a strict canonical transformation before insertion into the relational tables:
1. Content Sanitization: Strips ephemeral, non-structural tags (e.g., session tokens, variable tracking metrics, rendering metadata).
2. Alphabetical Key Serialization: Forces JSON strings to sort payload keys alphabetically to eliminate lexical variation across alternate ingestion paths.
3. Cryptographic Indexing: Generates a stable SHA-256 content hash from the canonical string. This serves as the system's primary tracking key.
4. Ingestion Anchoring: Commits records with a system-assigned, immutable wall-clock timestamp ($T_{\text{ingest}}$).
2.2 Point-in-Time (PIT) Simulation Boundary
To completely protect the machine learning backtesting engine from catastrophic lookahead bias, the system applies a rigid temporal filter during virtual simulation tasks. At any given playback step ($T_{\text{simulation}}$), the platform executes a hard database blind:
$$\text{Visible Context} = \{ \text{Data Rows} \mid T_{\text{ingest}} \le T_{\text{simulation}} \}$$ 
The Replay Identification Protocol
To bypass the live LLM layer entirely during backtest optimization loops—minimizing runtime latencies and API overhead—the AdaptiveAgentRunner implements an automated intercept layer:
• When an execution pass is requested, the system computes a unique context_fingerprint (a cumulative SHA-256 hash derived from the sorted array of visible ingestion IDs and the active prompt file configuration).
• The engine queries the agent_audit_log. If a historical record matching that exact fingerprint exists, the live neural network call is completely skipped. The pre-calculated, structured JSON output is immediately extracted from the database ledger and returned to the pipeline.

───

3. Self-Improving Agent Topology & Evolutionary Loop
LedgerQuant decouples tactical execution from strategic self-optimization through an asymmetric Dual-Agent Evolutionary Framework. This methodology allows the system to continuously refine its trading logic without mutating the underlying runtime source files.
unset
[ Ingested Market Context ] ────> [ EXECUTOR AGENT ] ────> [ Trade Signal ] ▲ │ │ (Optimized Prompt) ▼ [ Meta-Prompt Registry ] │ [ cBot Execution ] ▲ │ │ │ │ ▼ └───────── [ CRITIC AGENT (Optimizer) ] <─── [ Performance Ledger ]

3.1 Asynchronous Optimization Engine
• The Executor Node: A lean, stateless instance optimized for fast inference execution. It operates on fixed prompt layouts during active live sessions or specific backtest windows.
• The Critic Node: A large-context reasoning engine (e.g., Codex GPT-6 Astra) executed asynchronously via a scheduled background pipeline worker.
3.2 The Self-Improvement Sequence
1. Performance Extraction: The Critic agent pulls historical audit logs matching recent trading intervals, capturing both profitable entries and risk-driven rejections (e.g., instances where signals were discarded due to spread or slippage spikes).
2. Instruction Generation: The Critic evaluates the failures against the legacy instruction set and generates a revised system prompt, adding clear systemic behavioral rules to limit observed classification mistakes.
3. Automated Verification: The newly generated prompt version is backtested over historical validation datasets using cached context hashes. If it outpaces the legacy version's risk-adjusted profile, it is committed to the registry as the new operational standard.

───

4. Polymorphic Model Registry & Clean Architecture
To keep the application highly extensible and minimize code bloat, all agent parameters, validation contracts, and runtime states are decoupled from the implementation files.
4.1 Single Source of Truth Registry Structure
The system implements a centralized schema layer. Adding new agent responsibilities or updating analytical scopes requires simple data entries rather than code modifications:
python


───

5. Network Wire Protocol & Gateway Specifications
The communication between the Python application network and the external C# cBot engine relies on an asynchronous WebSocket pipeline managed by FastAPI. This interface features strict structural routing definitions and concrete fault circuit-breakers.
5.1 Dynamic Validation Wire Formats
All frames passing through the socket must strictly wrap their payloads inside a metadata routing layer.
Outbound Signal Frame (Python Server -> C# cBot)
json
{ "meta": { "version": "1.0.0", "timestamp": "2026-10-08T16:11:00Z", "message_type": "SIGNAL_DISPATCH", "correlation_id": "8f3b2a1c-9d8e-7f6a-5b4c-3d2e1f0a9b8c" }, "data": { "signal_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d", "agent_name": "MacroAnalyst", "symbol": "XAUUSD", "direction": "BUY", "regime_score": 2, "confidence": 0.89, "context_fingerprint": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855" } }

Inbound Execution Report (C# cBot -> Python Server)
json
{ "meta": { "version": "1.0.0", "timestamp": "2026-10-08T16:11:02Z", "message_type": "EXECUTION_REPORT", "correlation_id": "8f3b2a1c-9d8e-7f6a-5b4c-3d2e1f0a9b8c" }, "data": { "signal_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d", "status": "REJECTED_RISK", "broker_order_id": null, "filled_price": 0.0, "rejection_reason": "SPREAD_EXCEEDS_MAX_THRESHOLD", "execution_latency_ms": 142 } }

5.2 Transmission Resiliency Framework
• The Heartbeat Interval: The Python service issues an empty connection pulse frame every 10,000ms. The C# interface must respond with a confirmation within 2,000ms.
• The Safety Circuit-Breaker: If two consecutive transmission confirmations are missed, the C# client enters an immediate isolation state. It rejects subsequent trading frames, flags an internal connectivity failure, logs the incident locally, and applies trailing protection logic to active open exposure.
• The Token Gateway: Every socket initiation request must submit an explicit handshake string (X-Ledger-Auth). Connections missing valid parameter tokens are instantly rejected, shielding the internal database layers from outside scanning.