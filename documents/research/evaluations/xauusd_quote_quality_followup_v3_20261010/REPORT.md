# XAUUSD exploratory follow-up, version 3

**Status:** market-action hypothesis proposed; no economic effect measured, no
evaluation contract frozen, and no 2021 outcome opened.

On 10 October 2026, one `gpt-5.4-mini` Research → Critic run tested the
amended agent instructions using the operator-approved task (SHA-256
`ec1096c6bc5ab8ba792c419d551b1d2435247d1a3dc961c6549a65cb863cb919`).
The task included four already released source summaries and linked the
[parked parent](../xauusd_quote_quality_followup_v2_20261010/REPORT.md).
It contained no account number, API key, raw ticks or 2021 outcome. The run
ID is `4f5a5aa9-6add-4de0-8a94-fcd278ba5a70`; the provider returned
`gpt-5.4-mini-2026-03-17`.

Research proposed a 15-minute XAUUSD order-abstention overlay: use a
prior-30-minute spread-IQR rule and a quote-freshness check to decide whether
to skip otherwise eligible marketable orders. It identified the order
population as **hypothetical**, named taking those orders as the comparator,
and stated that the weak, development-exposed 2020 association does not show
an economic edge. The draft remains `EXPLORATORY_UNMEASURED`; it is not a
validated strategy. Its hash is
`fd25e0dd6b0cd0542d6a67f488c046e6eb0e194c0b1c17e750c8bf5cf2826263`.

Critic classified the draft as `MARKET_ACTION` with an `ECONOMIC_OUTCOME`
payoff and flagged the hypothetical order population, unknown decision-time
quote availability, unverified costs, and dependence among observations. Its
hash is `a04777c9bc1fdd97626fcf107f233b74f53431773208fc8acb69beec6e608b4f`.
Three provider invocations completed with no rejected tool calls. The provider
reported 7,163 input and 5,318 output tokens, with zero cached input and zero
cache-write tokens. The registry reserved USD 0.089541; this is **not** a
billed-cost measurement. Exact inputs, outputs, events and hashes remain in
the ignored local registry and
`data/research_control/operator/xauusd_quote_followup_v3_20261010/`.

## Operator assessment

The instruction change addressed the narrow problem under test: Research no
longer treats missing latency and cost measurements as a ban on proposing a
hypothesis. Critic recognizes the economic action and does not mistake the
proposal for a demonstrated payoff.

The proposed measurement is **not ready to freeze**. It asks to compare
*realized* execution cost and adverse fills for taken and skipped orders, but
skipped orders have no realized fill. That counterfactual needs an explicit
measurement design, such as shadow order intents with a declared quote-based
fill model, followed by prospective validation where feasible. An observed
strategy or order-intent population must be defined first; otherwise there
are no eligible trades whose abstention value can be estimated. The rule also
leaves its IQR threshold, freshness bound, broker-cost mapping, and baseline
comparison unspecified. Critic identified several of these gaps but did not
explicitly reject the impossible “realized cost of skipped orders” comparison.

The draft's reference to unopened 2021 data is a proposal for a future test,
not authorization to open that evidence. A measurement contract must specify
the counterfactual, order population, parameters and independent evaluation
boundary before any such test. The 2020 development result remains weak, so
this idea may reasonably be deprioritized after those prerequisites are
examined. No model-performance or trading-performance improvement has been
established by this single process run.
