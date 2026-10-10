# Process review: Research — e7f85e02

This is a derived reading view. All findings below are the recorded assessor's claims; exporting or reading this document does not approve them.

## What you are reviewing

> Original Astra v1 draft: binding cost declaration against a price-only scope.

- Recorded review state: **PROPOSED**.
- Assessor outcome exposure: **EXPOSED**.
- Recorded at: `2026-10-09T23:04:06.502713+00:00`.
- Exported at: `2026-10-09T23:32:27.378125+00:00`.
- Agent action time: `2026-10-09T20:01:55.318221+00:00`.

You are assessing whether each process allegation follows from the cited information and the rules then in force, including attribution, severity and applicability. A process review does not certify predictive value, trading profitability or general agent quality.

[Complete source packet and assessment](e7f85e02-research.source.json)

**Review availability:** awaiting human review.

## Decision key

- `SUPPORTED`: the alleged defect is supported by the evidence.
- `NOT_SUPPORTED`: the allegation is not supported; this is not a blanket quality certificate.
- `UNRESOLVED`: keep the question open and record what is missing.
- `REVIEWED`: a reviewer has assessed the record; it does not mean every allegation was accepted.

## Findings

### F1 — Current versus future data requirements

**Assessor's proposed label:** `SUPPORTED` — the alleged defect is supported.

**Component:** `research`. **Severity:** `material`.

**Claim to check:**

> data\_requirements\[0\] declares broker\_costs as required data while its own reason says costs block only economic interpretation, not the present no-trade diagnostic. Under the v1 contract the typed field was binding, so the declaration blocked the attempt. The later BLOCKED\_CONTRACT\_DEFECT annotation classifies this as a contract defect of the draft, not as missing price data or absent predictive value.

**Applicability claimed:**

> v1 proposals whose required-data field is binding: a deferred cost prerequisite must not be declared as current required data.

**Exact cited source values:**

Source: `draft.data_requirements[0]`

```json
{
  "reactivation_condition": "Only reconsider an execution-oriented extension after independently verified, timestamp-aligned broker spread, commission and slippage evidence becomes available and a separate authorization process permits that research.",
  "reason": "Broker execution costs are unverified. This blocks economic interpretation, not the present no-trade price diagnostic, and is not evidence of absent predictive value.",
  "source": "broker_costs"
}
```

Source: `draft.mechanism`

> Declare only 12 UTC, not the known-duplicate all-hours rule. The testable conjecture is that prior-hour midquote direction during the European trading day may persist over the next four hours as activity transitions toward the US session. Restricting the clock hour reduces mixing with morning and late-day conditions, but fixed UTC hours do not perfectly track daylight-saving session shifts. This is a mechanism conjecture, not measured order-flow evidence. Use exactly the catalog momentum-sign rule with its registered label and tie semantics; add no filters or alternative rules. The hour choice is mechanism-motivated, not selected by a performance comparison. Admissibility probability 0.80 is my pre-review belief that this bounded exploratory proposal is admissible, not a probability of predictive success.

**Your decision:** retain or change the label, component, severity or explanation. If the sources do not establish the claim, use `NOT_SUPPORTED` or `UNRESOLVED` and explain the limitation. No decision has been selected for you.

### F2 — Evidence attributed to the wrong scope

**Assessor's proposed label:** `NOT_SUPPORTED` — the alleged defect is not supported.

**Component:** `research`. **Severity:** `advisory`.

**Claim to check:**

> Support and contrary evidence explicitly label the released 2020 and 2021 results as prior all-hours results that do not measure the 12 UTC subset.

**Applicability claimed:**

> Attribution of released aggregate results to a proposed subset.

**Exact cited source values:**

Source: `draft.support`

```json
[
  "The registered catalog permits 12 UTC and the exact prior-hour momentum-sign rule with a four-hour horizon, enabling a bounded price-only test without additional data or execution.",
  "eurusd_four_hour_direction_2020_v1 supplies limited motivation to inspect directional continuation: released candidate accuracy 0.5242966752 versus baseline 0.4629156010, with paired difference 0.0613810742. These are prior all-hours results, not results for this proposal.",
  "The bounded development page demonstrates available case statuses, target labels and settlement provenance, including a measurable 12 UTC case. It supports diagnostic feasibility only, not predictive value or a support-count claim."
]
```

Source: `draft.contrary_evidence`

```json
[
  "eurusd_four_hour_direction_2021_replication_v1 failed temporally: candidate accuracy 0.4717223650 versus baseline 0.4935732648; paired difference -0.0218508997 and bootstrap lower bound -0.0644329897. This weighs against stable momentum, but does not establish that every hour subset fails.",
  "The released 2020 all-hours advantage weakened from 0.1111111111 in Q3 to 0.0103626943 in Q4. Neither released aggregate establishes an advantage at 12 UTC.",
  "The inspected development page includes a missing 2020-01-01 12 UTC input and an incorrect 2020-01-02 12 UTC candidate prediction. This small page cannot establish subset accuracy or sufficient support.",
  "All independent windows are consumed. Historical quote visibility is assumed, many 2020 bid/ask pairs are equal, and execution costs remain COST_UNVERIFIED; no confirmatory, model-quality or economic-edge claim is justified."
]
```

**Your decision:** retain or change the label, component, severity or explanation. If the sources do not establish the claim, use `NOT_SUPPORTED` or `UNRESOLVED` and explain the limitation. No decision has been selected for you.

### F3 — Missing contrary evidence

**Assessor's proposed label:** `NOT_SUPPORTED` — the alleged defect is not supported.

**Component:** `research`. **Severity:** `advisory`.

**Claim to check:**

> The draft cites the 2021 temporal failure, the Q3-to-Q4 weakening, the limited development page and the consumed windows.

**Applicability claimed:**

> Completeness of contrary evidence available in the released records.

**Exact cited source values:**

Source: `draft.contrary_evidence`

```json
[
  "eurusd_four_hour_direction_2021_replication_v1 failed temporally: candidate accuracy 0.4717223650 versus baseline 0.4935732648; paired difference -0.0218508997 and bootstrap lower bound -0.0644329897. This weighs against stable momentum, but does not establish that every hour subset fails.",
  "The released 2020 all-hours advantage weakened from 0.1111111111 in Q3 to 0.0103626943 in Q4. Neither released aggregate establishes an advantage at 12 UTC.",
  "The inspected development page includes a missing 2020-01-01 12 UTC input and an incorrect 2020-01-02 12 UTC candidate prediction. This small page cannot establish subset accuracy or sufficient support.",
  "All independent windows are consumed. Historical quote visibility is assumed, many 2020 bid/ask pairs are equal, and execution costs remain COST_UNVERIFIED; no confirmatory, model-quality or economic-edge claim is justified."
]
```

**Your decision:** retain or change the label, component, severity or explanation. If the sources do not establish the claim, use `NOT_SUPPORTED` or `UNRESOLVED` and explain the limitation. No decision has been selected for you.

### F4 — Predictive falsification versus admission rules

**Assessor's proposed label:** `NOT_SUPPORTED` — the alleged defect is not supported.

**Component:** `research`. **Severity:** `advisory`.

**Claim to check:**

> The falsifier conditions a nonpositive paired accuracy difference on support and data-quality thresholds and separates blocked support from disproof.

**Applicability claimed:**

> Falsifiers must name a predictive condition, not an administrative one.

**Exact cited source values:**

Source: `draft.falsifier`

> Apply the catalog unchanged to the declared 12 UTC weekday subset of the permitted 2020-01-01 through 2020-07-01 exclusive development window: retain holidays, the one-second decision delay, 60-second quote-age and settlement-delay limits, and the registered majority-development-target baseline with NON\_UP ties. Fewer than 100 eligible anchors or missing fraction above 0.10 blocks an interpretable comparison rather than proving no predictive value. With adequate support and quality, a nonpositive paired candidate-minus-baseline accuracy difference contradicts the proposed directional continuation in this diagnostic window. A positive difference is merely exploratory and does not establish transport, confirmatory success, model quality or profitability. Do not search other hour subsets after observing the result. No independent validation window is available.

**Your decision:** retain or change the label, component, severity or explanation. If the sources do not establish the claim, use `NOT_SUPPORTED` or `UNRESOLVED` and explain the limitation. No decision has been selected for you.

## Assessor limitations

> Retrospective sealed-packet assessment authored by an AI operator under explicit user authorization; review\_state PROPOSED until a human reviewer supersedes it with REVIEWED.

> The assessor had read later development results, corrections and the 2.12/2.13 audit before assessing; this is not an ex-ante assessment.

> The v1 contract had no explicit requirement scope; the defect is the use of the binding field for a deferred prerequisite under the rules then in force.

## Original task

```json
{
  "candidate_limit": 1,
  "evidence_mode": "retrospective_engineering",
  "execution_allowed": false,
  "feedback_policy": "structured_released_evidence/1",
  "purpose": "Propose one bounded price-only EURUSD diagnostic using the registered catalog and released evidence. Explain its mechanism, contrary evidence and falsifier. Critic must review the exact draft independently of the Research conversation.",
  "validation_access": "none",
  "version": "eurusd_agent_bootstrap/1"
}
```

## Original draft

```json
{
  "admissibility_probability": 0.8,
  "contrary_evidence": [
    "eurusd_four_hour_direction_2021_replication_v1 failed temporally: candidate accuracy 0.4717223650 versus baseline 0.4935732648; paired difference -0.0218508997 and bootstrap lower bound -0.0644329897. This weighs against stable momentum, but does not establish that every hour subset fails.",
    "The released 2020 all-hours advantage weakened from 0.1111111111 in Q3 to 0.0103626943 in Q4. Neither released aggregate establishes an advantage at 12 UTC.",
    "The inspected development page includes a missing 2020-01-01 12 UTC input and an incorrect 2020-01-02 12 UTC candidate prediction. This small page cannot establish subset accuracy or sufficient support.",
    "All independent windows are consumed. Historical quote visibility is assumed, many 2020 bid/ask pairs are equal, and execution costs remain COST_UNVERIFIED; no confirmatory, model-quality or economic-edge claim is justified."
  ],
  "data_requirements": [
    {
      "reactivation_condition": "Only reconsider an execution-oriented extension after independently verified, timestamp-aligned broker spread, commission and slippage evidence becomes available and a separate authorization process permits that research.",
      "reason": "Broker execution costs are unverified. This blocks economic interpretation, not the present no-trade price diagnostic, and is not evidence of absent predictive value.",
      "source": "broker_costs"
    }
  ],
  "diagnostic": {
    "candidate_rule": "prior_hour_midquote_momentum_sign",
    "catalog_version": "eurusd_direction/1",
    "horizon_seconds": 14400,
    "hours_utc": [
      12
    ],
    "instrument": "EURUSD",
    "lookback_seconds": 3600,
    "orders_allowed": false
  },
  "evidence_ids": [
    "eurusd_four_hour_direction_2020_v1",
    "eurusd_four_hour_direction_2021_replication_v1"
  ],
  "falsifier": "Apply the catalog unchanged to the declared 12 UTC weekday subset of the permitted 2020-01-01 through 2020-07-01 exclusive development window: retain holidays, the one-second decision delay, 60-second quote-age and settlement-delay limits, and the registered majority-development-target baseline with NON_UP ties. Fewer than 100 eligible anchors or missing fraction above 0.10 blocks an interpretable comparison rather than proving no predictive value. With adequate support and quality, a nonpositive paired candidate-minus-baseline accuracy difference contradicts the proposed directional continuation in this diagnostic window. A positive difference is merely exploratory and does not establish transport, confirmatory success, model quality or profitability. Do not search other hour subsets after observing the result. No independent validation window is available.",
  "mechanism": "Declare only 12 UTC, not the known-duplicate all-hours rule. The testable conjecture is that prior-hour midquote direction during the European trading day may persist over the next four hours as activity transitions toward the US session. Restricting the clock hour reduces mixing with morning and late-day conditions, but fixed UTC hours do not perfectly track daylight-saving session shifts. This is a mechanism conjecture, not measured order-flow evidence. Use exactly the catalog momentum-sign rule with its registered label and tie semantics; add no filters or alternative rules. The hour choice is mechanism-motivated, not selected by a performance comparison. Admissibility probability 0.80 is my pre-review belief that this bounded exploratory proposal is admissible, not a probability of predictive success.",
  "predicted_failure": "TEMPORAL_FAILURE",
  "sha256": "a09b3f29fc094bf0eb810a9953d9756f6bb428282b0c71c1b2495f89d144f034",
  "support": [
    "The registered catalog permits 12 UTC and the exact prior-hour momentum-sign rule with a four-hour horizon, enabling a bounded price-only test without additional data or execution.",
    "eurusd_four_hour_direction_2020_v1 supplies limited motivation to inspect directional continuation: released candidate accuracy 0.5242966752 versus baseline 0.4629156010, with paired difference 0.0613810742. These are prior all-hours results, not results for this proposal.",
    "The bounded development page demonstrates available case statuses, target labels and settlement provenance, including a measurable 12 UTC case. It supports diagnostic feasibility only, not predictive value or a support-count claim."
  ],
  "title": "Exploratory 12 UTC EURUSD prior-hour momentum direction diagnostic"
}
```

## Catalog and requirement rules actually supplied

Source: `tool_results[0].result.catalog`

```json
{
  "baseline_rule": "majority_development_target_class",
  "baseline_tie": "PREDICT_NON_UP",
  "candidate_rule": "prior_hour_midquote_momentum_sign",
  "decision_delay_seconds": 1,
  "development_end": "2020-07-01T00:00:00Z",
  "development_start": "2020-01-01T00:00:00Z",
  "economic_claim": "none_predictive_diagnostic_only",
  "horizon_seconds": 14400,
  "include_holidays": true,
  "inference_policy": "exploratory_only_no_confirmatory_pass",
  "instrument": "EURUSD",
  "iso_weekdays": [
    1,
    2,
    3,
    4,
    5
  ],
  "lookback_seconds": 3600,
  "maximum_missing_fraction": 0.1,
  "maximum_quote_age_seconds": 60,
  "maximum_settlement_delay_seconds": 60,
  "minimum_eligible_anchors": 100,
  "orders_allowed": false,
  "permitted_hours_utc": [
    8,
    12,
    16
  ],
  "search_policy": "one_declared_candidate_no_optimization",
  "validation_policy": "NO_INDEPENDENT_WINDOW",
  "version": "eurusd_direction/1"
}
```

## Rules and test-basis context

The complete source export contains the task, tool results and frozen context. The following test-basis annotations and service checks are retrospective context, not statements authored by the agent.

```json
{
  "instruction_sha256": "a1030d14f2f6e374e91e3c6e7ce2611ff3cf1ab7a53f6740ee02aee83ad7abae",
  "research_contract_version": null,
  "role": "research",
  "tool_policy": "research_tools/1",
  "tool_schema_sha256": "f04fd6943c956bd1d4bf74c27861ccd4bc70a189659408b5f21c28b3bf7f9f06",
  "workflow": "discovery"
}
```

```json
{
  "context_invalidated": false,
  "disputed_service_output": false,
  "review_corrections": [
    {
      "actor": "codex_operator_under_explicit_user_revision_clarification",
      "classification": "BLOCKED_CONTRACT_DEFECT",
      "correction_sha256": "132e3358e814560d845fa4f83453d929e5d33b1398fe0bad5e30747877f9aa04",
      "reason": "Operator clarification: the binding v1 broker-cost declaration conflicted with the stated price-only scope. This is a contract defect eligible for a linked scope correction, not proof of missing price data or absent predictive value."
    }
  ]
}
```

```json
{
  "policy": "deterministic contract checks recomputed under current code; not an outcome",
  "reasons": [
    "SOURCE_UNAVAILABLE"
  ],
  "status": "BLOCKED_DATA_REQUIREMENT"
}
```

## Recording your review

Keep the original record. Submit a new `assess-process` command only after making your decisions: `supersedes` names the assessment below, `reviewer` identifies the human reviewer, and the new assessor declares their actual outcome exposure. Retain unresolved findings where appropriate. Original authorship and declarations remain in the superseded record.

Before submission, regenerate this view to check for changed or superseded sources. Only your explicit review decision permits recording a reviewed replacement.

## Audit metadata

Assessment to supersede: `bbbfaa970ed0e53235dfd5057c55a00ca8f8f6244f93232171c874a822882cb7`.

Packet hash: `b7ed262f2f031cdd496a933d68b12369d2d5b09a9ef467909f8bc059741f4296`.

Original assessor:

> claude\_operator\_under\_explicit\_user\_authorization\_20261010

Registry integrity at export:

```json
{
  "state": "SUSPENDED",
  "reasons": [
    "NOT_REVIEWED"
  ],
  "review_state": "PROPOSED",
  "run_id": "e7f85e02-fe52-473b-a786-6e659ae2f246",
  "role": "research",
  "sha256": "bbbfaa970ed0e53235dfd5057c55a00ca8f8f6244f93232171c874a822882cb7",
  "created_at": "2026-10-09T23:04:06.502713+00:00"
}
```
