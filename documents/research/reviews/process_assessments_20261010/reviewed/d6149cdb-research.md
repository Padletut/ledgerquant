# Process review: Research — d6149cdb

This is a derived reading view of a completed review. The findings preserve its recorded decisions; exporting or reading this document does not change them.

## Recorded review

> Explicit human review supplied in the project conversation on 10 October 2026; Codex transcribed the finding decisions and limitations. Original assessment retained by supersession; no new agent inference or market evaluation. v3 corrected revision: agent contributions were correct; substantive content was service-constructed from the authorized parent.

- Recorded review state: **REVIEWED**.
- Assessor outcome exposure: **EXPOSED**.
- Recorded at: `2026-10-10T00:26:11.745757+00:00`.
- Exported at: `2026-10-10T00:26:17.454911+00:00`.
- Agent action time: `2026-10-09T21:17:48.142557+00:00`.

You are assessing whether each process allegation follows from the cited information and the rules then in force, including attribution, severity and applicability. A process review does not certify predictive value, trading profitability or general agent quality.

[Complete source packet and assessment](d6149cdb-research.source.json)

**Review availability:** CURRENT

## Decision key

- `SUPPORTED`: the alleged defect is supported by the evidence.
- `NOT_SUPPORTED`: the allegation is not supported; this is not a blanket quality certificate.
- `UNRESOLVED`: keep the question open and record what is missing.
- `REVIEWED`: a reviewer has assessed the record; it does not mean every allegation was accepted.

## Findings

### F1 — Evidence attributed to the wrong scope

**Reviewed finding:** `NOT_SUPPORTED` — the alleged defect is not supported.

**Component:** `research`. **Severity:** `advisory`.

**Recorded explanation:**

> All evidence claims are typed SOURCE\_CONTRACT and describe the released results as family aggregates. The wording 'all-hours' for the registered \[8,12,16\] anchors was resolved by the operator as inherited wording, not misattribution.

**Applicability claimed:**

> Scope of cited released facts.

**Exact cited source values:**

Source: `draft.evidence_claims`

```json
[
  {
    "applies_to": "SOURCE_CONTRACT",
    "fact_id": "12c4ed740773044b65d3154f16b123641c006fd7ace03e50651c828bdbbbfcdb",
    "interpretation": "The released 2020 all-hours evaluation for the same rule family showed candidate_accuracy 0.5242966752 versus baseline 0.4629156010. This supports keeping the family in view, but it is aggregate evidence and does not measure the 12 UTC subset."
  },
  {
    "applies_to": "SOURCE_CONTRACT",
    "fact_id": "c777a1433df16553e713fbf9436a283b5443e4d041ab8a6b248c856586ec7d2f",
    "interpretation": "The 2020 all-hours baseline_accuracy of 0.4629156010 is a benchmark for the released aggregate diagnostic only; it cannot be repurposed as 12 UTC subset performance."
  },
  {
    "applies_to": "SOURCE_CONTRACT",
    "fact_id": "8b28beab9b525ce1b347be59c4de4bd36dede627f9b5625d04aa6e06329d7bbb",
    "interpretation": "The 2021 replication gate decision TEMPORAL_FAILED is contrary evidence for the same all-hours family and shows later instability, but it still does not falsify the 12 UTC subset by itself."
  },
  {
    "applies_to": "SOURCE_CONTRACT",
    "fact_id": "a2e83f808feabf35c02ce41c6c3e4cc62374ecd92fe99c4361e381c2720a7eb3",
    "interpretation": "The 2021 all-hours paired_accuracy_difference of -0.0218508997 is negative aggregate evidence for the related family, again not a subset measurement and not a basis for claiming the 12 UTC variant was tested."
  }
]
```

### F2 — Same idea, duplicate or linked revision

**Reviewed finding:** `NOT_SUPPORTED` — the alleged defect is not supported.

**Component:** `research`. **Severity:** `advisory`.

**Recorded explanation:**

> prior\_comparisons mark the parent signature SAME\_RESEARCH\_IDEA and the \[8,12,16\] family RELATED\_VARIANT, with the authorized revision link.

**Applicability claimed:**

> Linking a repeated market idea to its earlier attempt.

**Exact cited source values:**

Source: `draft.prior_comparisons`

```json
[
  {
    "difference": "Same candidate_rule, horizon, instrument, lookback, and 12 UTC focus as the parent; this submission is the authorized cost-scope-only correction that classifies broker_costs as future_economic rather than a current blocker.",
    "relation": "SAME_RESEARCH_IDEA",
    "signature": "24c3c3e2b3d52116469ac293d2be78ea9778a0a5cb3cb0628825b04c701e36b5"
  },
  {
    "difference": "Broader all-hours family variant using [8,12,16] rather than the single 12 UTC subset; related exposure, but not the corrected 12 UTC contract itself.",
    "relation": "RELATED_VARIANT",
    "signature": "2dceefbecd63b41726bf86d3fbfd2397c5e91fe4c9737433dcc23757c7598188"
  }
]
```

### F3 — Current versus future data requirements

**Reviewed finding:** `NOT_SUPPORTED` — the alleged defect is not supported.

**Component:** `research`. **Severity:** `advisory`.

**Recorded explanation:**

> The service applied the authorized future\_economic patch; no current cost requirement remains.

**Applicability claimed:**

> Scope declaration of deferred cost prerequisites.

**Exact cited source values:**

Source: `draft.data_requirements[0]`

```json
{
  "reactivation_condition": "Only reconsider an execution-oriented extension after independently verified, timestamp-aligned broker spread, commission and slippage evidence becomes available and a separate authorization process permits that research.",
  "reason": "Broker execution costs are unverified. This blocks economic interpretation, not the present no-trade price diagnostic, and is not evidence of absent predictive value.",
  "scope": "future_economic",
  "source": "broker_costs"
}
```

### F4 — Predictive falsification versus admission rules

**Reviewed finding:** `NOT_SUPPORTED` — the alleged defect is not supported.

**Component:** `research`. **Severity:** `advisory`.

**Recorded explanation:**

> The inherited falsifier is predictive and conditions disproof on support and data quality.

**Applicability claimed:**

> Falsifiers must name a predictive condition.

**Exact cited source values:**

Source: `draft.falsifier`

> Apply the catalog unchanged to the declared 12 UTC weekday subset of the permitted 2020-01-01 through 2020-07-01 exclusive development window: retain holidays, the one-second decision delay, 60-second quote-age and settlement-delay limits, and the registered majority-development-target baseline with NON\_UP ties. Fewer than 100 eligible anchors or missing fraction above 0.10 blocks an interpretable comparison rather than proving no predictive value. With adequate support and quality, a nonpositive paired candidate-minus-baseline accuracy difference contradicts the proposed directional continuation in this diagnostic window. A positive difference is merely exploratory and does not establish transport, confirmatory success, model quality or profitability. Do not search other hour subsets after observing the result. No independent validation window is available.

## Assessor limitations

> Human finding decisions supplied via the project conversation and transcribed by Codex. The reviewer and transcribing assessor are outcome-exposed; REVIEWED does not imply an outcome-blind assessment.

> The assessor had read later development results, corrections and the 2.12/2.13 audit before assessing; this is not an ex-ante assessment.

> The revision's diagnostic, rationale and falsifier were copied from the parent by the service; the agent authored only prior comparisons, evidence claims, admission risks and its current admissibility belief.

> Much substantive proposal content was inherited or service-constructed. Absence of these defects does not establish newly acquired independent Research capability.

## Original task

```json
{
  "confirmatory_tests": 0,
  "engineering_recovery_of_run_id": "10972e1f-0613-4984-951d-7a01e1a37199",
  "parent_campaigns": [
    "openai_astra_bootstrap_20261009",
    "openai_mini_requirements_20261009"
  ],
  "proposal_limit": 1,
  "purpose": "Submit exactly one authorized corrected contract revision of the existing 12 UTC research idea. Use submit_contract_revision after reading all required tools. Do not propose another diagnostic. The service preserves the parent rationale and only corrects broker_costs scope. Cite both released aggregate outcomes without treating them as subset measurements.",
  "recovery_reason": "Prior attempt stopped with max_output_tokens before submitting any draft; preserve failure and repeat the same authorized cost-scope correction once with a larger response limit.",
  "related_attempt_ids": [
    "e7f85e02-fe52-473b-a786-6e659ae2f246",
    "23632117-fb7e-40c6-bffc-b9bbc39df16e"
  ],
  "revision_authorizations": [
    {
      "parent_draft_id": "e7f85e02-fe52-473b-a786-6e659ae2f246",
      "parent_draft_sha256": "a09b3f29fc094bf0eb810a9953d9756f6bb428282b0c71c1b2495f89d144f034",
      "reason": "User explicitly authorized the same research idea to receive a cost-scope-only corrected attempt with full ancestry and unchanged exposure.",
      "scope_changes": [
        {
          "requirement_index": 0,
          "scope": "future_economic"
        }
      ]
    }
  ],
  "stop_after": "One revision and one critique; operator review, then design freeze, fixed development and candidate lock only if admissible. No replacement sampling.",
  "submission_policy": "revision_only",
  "validation_status": "NO_INDEPENDENT_WINDOW",
  "version": "grounded_revision_task/3"
}
```

## Original draft

```json
{
  "admissibility_probability": 0.78,
  "admission_risks": [
    "Authorized cost-scope correction is narrow: if the parent broker_costs requirement is treated as current rather than future_economic, the attempt remains a contract defect rather than a predictive refutation.",
    "The 2021 all-hours replication failed temporally, so stability across later data remains doubtful even though that result does not measure the 12 UTC subset.",
    "The released outcomes are all-hours family aggregates; attributing them to the 12 UTC subset would be an attribution error.",
    "Historical quote visibility is assumed and execution costs remain unverified; no economic or trading claim is established by this diagnostic.",
    "A single subset revision still shares the same exposed research family, so duplicate-idea scrutiny remains material."
  ],
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
      "scope": "future_economic",
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
  "evidence_claims": [
    {
      "applies_to": "SOURCE_CONTRACT",
      "fact_id": "12c4ed740773044b65d3154f16b123641c006fd7ace03e50651c828bdbbbfcdb",
      "interpretation": "The released 2020 all-hours evaluation for the same rule family showed candidate_accuracy 0.5242966752 versus baseline 0.4629156010. This supports keeping the family in view, but it is aggregate evidence and does not measure the 12 UTC subset."
    },
    {
      "applies_to": "SOURCE_CONTRACT",
      "fact_id": "c777a1433df16553e713fbf9436a283b5443e4d041ab8a6b248c856586ec7d2f",
      "interpretation": "The 2020 all-hours baseline_accuracy of 0.4629156010 is a benchmark for the released aggregate diagnostic only; it cannot be repurposed as 12 UTC subset performance."
    },
    {
      "applies_to": "SOURCE_CONTRACT",
      "fact_id": "8b28beab9b525ce1b347be59c4de4bd36dede627f9b5625d04aa6e06329d7bbb",
      "interpretation": "The 2021 replication gate decision TEMPORAL_FAILED is contrary evidence for the same all-hours family and shows later instability, but it still does not falsify the 12 UTC subset by itself."
    },
    {
      "applies_to": "SOURCE_CONTRACT",
      "fact_id": "a2e83f808feabf35c02ce41c6c3e4cc62374ecd92fe99c4361e381c2720a7eb3",
      "interpretation": "The 2021 all-hours paired_accuracy_difference of -0.0218508997 is negative aggregate evidence for the related family, again not a subset measurement and not a basis for claiming the 12 UTC variant was tested."
    }
  ],
  "evidence_ids": [
    "eurusd_four_hour_direction_2020_v1",
    "eurusd_four_hour_direction_2021_replication_v1"
  ],
  "falsification_target": "predictive_performance",
  "falsifier": "Apply the catalog unchanged to the declared 12 UTC weekday subset of the permitted 2020-01-01 through 2020-07-01 exclusive development window: retain holidays, the one-second decision delay, 60-second quote-age and settlement-delay limits, and the registered majority-development-target baseline with NON_UP ties. Fewer than 100 eligible anchors or missing fraction above 0.10 blocks an interpretable comparison rather than proving no predictive value. With adequate support and quality, a nonpositive paired candidate-minus-baseline accuracy difference contradicts the proposed directional continuation in this diagnostic window. A positive difference is merely exploratory and does not establish transport, confirmatory success, model quality or profitability. Do not search other hour subsets after observing the result. No independent validation window is available.",
  "mechanism": "Declare only 12 UTC, not the known-duplicate all-hours rule. The testable conjecture is that prior-hour midquote direction during the European trading day may persist over the next four hours as activity transitions toward the US session. Restricting the clock hour reduces mixing with morning and late-day conditions, but fixed UTC hours do not perfectly track daylight-saving session shifts. This is a mechanism conjecture, not measured order-flow evidence. Use exactly the catalog momentum-sign rule with its registered label and tie semantics; add no filters or alternative rules. The hour choice is mechanism-motivated, not selected by a performance comparison. Admissibility probability 0.80 is my pre-review belief that this bounded exploratory proposal is admissible, not a probability of predictive success.",
  "predicted_failure": "TEMPORAL_FAILURE",
  "prior_comparisons": [
    {
      "difference": "Same candidate_rule, horizon, instrument, lookback, and 12 UTC focus as the parent; this submission is the authorized cost-scope-only correction that classifies broker_costs as future_economic rather than a current blocker.",
      "relation": "SAME_RESEARCH_IDEA",
      "signature": "24c3c3e2b3d52116469ac293d2be78ea9778a0a5cb3cb0628825b04c701e36b5"
    },
    {
      "difference": "Broader all-hours family variant using [8,12,16] rather than the single 12 UTC subset; related exposure, but not the corrected 12 UTC contract itself.",
      "relation": "RELATED_VARIANT",
      "signature": "2dceefbecd63b41726bf86d3fbfd2397c5e91fe4c9737433dcc23757c7598188"
    }
  ],
  "revision": {
    "change_kind": "DATA_REQUIREMENT_SCOPE_CORRECTION",
    "parent_draft_id": "e7f85e02-fe52-473b-a786-6e659ae2f246",
    "parent_draft_sha256": "a09b3f29fc094bf0eb810a9953d9756f6bb428282b0c71c1b2495f89d144f034",
    "reason": "Authorized revision of the parent exploratory 12 UTC EURUSD prior-hour momentum diagnostic, preserving the parent diagnostic and rationale while correcting the broker_costs requirement to future_economic. The revised contract remains a no-trade, price-only diagnostic; the cost prerequisite is deferred rather than treated as a current blocker. Released aggregate evidence is cited only as family-level motivation and contrary evidence, not as subset measurements. This revision does not add a new diagnostic or extend the source beyond the approved contract family.",
    "scope_changes": [
      {
        "requirement_index": 0,
        "scope": "future_economic"
      }
    ]
  },
  "schema_version": "research_proposal/3",
  "sha256": "df1bc355a480b211da53a156c0d08450c69776594e0e2f46654cd99d6ed00537",
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

Source: `tool_results[0].result.requirement_rules`

> Every v2 data requirement has an explicit scope:
> current\_diagnostic blocks this attempt when the source is unavailable;
> future\_economic records a deferred prerequisite and does not block this price
> diagnostic or grant economic eligibility. Requiring broker\_costs for the current
> no-orders, no-economic-claim catalog is REQUIREMENT\_CONTRADICTION, a contract
> rejection, never a measured COST\_FAILURE. Raw news or historical sentiment
> required now remains BLOCKED\_DATA\_REQUIREMENT, pending data and a reviewed
> catalog extension. Do not silently execute an unsupported event-conditioned rule.
> Check mechanism, support and falsifier against these structured scopes. A claim
> to use a source now while deferring its requirement is a narrative contradiction.
> Preserve it as a material REQUIREMENT\_CONTRADICTION objection for operator review.

## Rules and test-basis context

The complete source export contains the task, tool results and frozen context. The following test-basis annotations and service checks are retrospective context, not statements authored by the agent.

```json
{
  "instruction_sha256": "922e70f4b7a033bf59c53517747b8db436b0de82c607edf1606dd2828f38df30",
  "research_contract_version": 3,
  "role": "research",
  "tool_policy": "research_tools/1",
  "tool_schema_sha256": "59d1e3ecce358e079f82107c639c1985586ba663e6663724b014161136811c35",
  "workflow": "discovery"
}
```

```json
{
  "context_invalidated": false,
  "disputed_service_output": true,
  "review_corrections": [
    {
      "actor": "codex_operator_reference_boundary_review",
      "classification": "CITATION_NAMESPACE_DEFECT",
      "correction_sha256": "1f067d6c99bb923d578532df2b76e4ac6e33a211a951f1ce102d18f771900231",
      "reason": "Architecture 2.11.1 reference policy scoped_registry_references/1 resolves exact frozen fact hashes as well as evidence-record IDs. The original UNKNOWN_EVIDENCE rejection treated two valid in-context fact hashes as unknown. Proposal and Critic output remain unchanged; arbitrary hashes still fail. Reassessment is deterministic, with no new inference, measurements or validation exposure."
    }
  ]
}
```

```json
{
  "policy": "deterministic contract checks recomputed under current code; not an outcome",
  "reasons": [
    "CRITIQUE_RECORDED_NOT_AN_APPROVAL"
  ],
  "status": "AWAITING_OPERATOR_REVIEW"
}
```

## Recording a further review

Keep the original record. Submit a new `assess-process` command only after making your decisions: `supersedes` names the assessment below, `reviewer` identifies the human reviewer, and the new assessor declares their actual outcome exposure. Retain unresolved findings where appropriate. Original authorship and declarations remain in the superseded record.

Before submission, regenerate this view to check for changed or superseded sources. Only your explicit review decision permits recording a reviewed replacement.

## Audit metadata

Assessment to supersede: `2037bd14051a3891f24871c4c6ad3ee88ee326a6145723d9b2b5749b026f35e7`.

Packet hash: `733a9c570add616bf16b00175e5c0a7a9a6f41ac2d3dc421628bd3cc8da96071`.

Original assessor:

> codex\_operator\_transcribing\_human\_review\_20261010

Registry integrity at export:

```json
{
  "state": "CURRENT",
  "reasons": [],
  "review_state": "REVIEWED",
  "run_id": "d6149cdb-bc86-47bb-8857-d0225010c35e",
  "role": "research",
  "sha256": "2037bd14051a3891f24871c4c6ad3ee88ee326a6145723d9b2b5749b026f35e7",
  "created_at": "2026-10-10T00:26:11.745757+00:00"
}
```

Recorded reviewer:

> human\_user\_via\_chat\_20261010

Superseded assessment:

> 6c25a7ded14792b90c8b0cf85bdd2db80568a4042a7349bc6b91339da952a2c2
