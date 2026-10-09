# Same research idea, corrected contract attempt

**Date:** 09 October 2026. **Architecture at execution:** working revision 2.11.1, consolidated into [2.12](../../../ARCHITECTURE.md) in commit `79cbbae`. The working revision was not committed separately; the additional planned 2.12 feedback/exposure gates were not part of this execution.
**Mode:** exposed process regression and retrospective development diagnostic.

## Implemented distinction

A market diagnostic signature identifies the idea within the finite catalog.
A draft/run identifies an attempt. A scope-only correction can be admitted as a
new `CORRECTED_REVISION` of the same idea, with the original parent ID/hash,
unchanged market contract and inherited exposure. Every attempt still counts.

The first supported revision changes the original `broker_costs` declaration to
`future_economic`. The service applies the authorized patch and preserves the
parent's diagnostic, rationale, evidence IDs and predictive falsifier. Agent
annotations and its current admissibility belief are separately recorded.
An unlinked repeat cannot claim a new idea; a valid linked correction can proceed.

Research and Critic share a frozen prior inventory and exact evidence facts.
Comparisons include blocked/rejected attempts. Facts identify their measured
diagnostic, window and baseline. Typed checks prevent attributing an aggregate
result to the 12 UTC subset. Narrative correctness remains subject to review.

## Historical corrections and actual lineage

| Attempt | Recorded result and subsequent interpretation |
| --- | --- |
| `e7f85e02-fe52-473b-a786-6e659ae2f246` | Original Astra draft; original data block retained, annotated `BLOCKED_CONTRACT_DEFECT` |
| `23632117-fb7e-40c6-bffc-b9bbc39df16e` | Original Mini repeat; original duplicate rejection retained, annotated `SAME_IDEA_REVISION_CANDIDATE` |
| `10972e1f-0613-4984-951d-7a01e1a37199` | Initial v3 attempt; output truncated before submission; no draft or economic failure |
| `d6149cdb-bc86-47bb-8857-d0225010c35e` | Completed v3 correction, explicitly parented to the first attempt; subsequently admitted, developed and locked |

The completed correction keeps signature
`24c3c3e2b3d52116469ac293d2be78ea9778a0a5cb3cb0628825b04c701e36b5`
and parent hash
`a09b3f29fc094bf0eb810a9953d9756f6bb428282b0c71c1b2495f89d144f034`.
Its own draft hash is
`df1bc355a480b211da53a156c0d08450c69776594e0e2f46654cd99d6ed00537`.
All remain in `eurusd_four_hour_direction`. Original measurements, attempts and
consumed windows were not removed or reset. The append-only
[review annotations](review_corrections.json) do not grant admission themselves.

## Frozen process regression

Three exposed templates × two repetitions × three arms produced 18 runs:
authorized scope correction, unlinked repeat and aggregate-as-subset attribution.
References were fixed before calls and excluded from model input. Changes to
context, schema, instructions and service checks form a combined intervention;
component-level attribution and broader discovery quality are unmeasured.

| Arm | Correct disposition and reason / planned | Technical failures |
| --- | ---: | ---: |
| Single agent | 4 / 6 | 0 |
| Research + Critic | 4 / 6 | 0 |
| Deterministic checklist | 6 / 6 | 0 |

Both model arms failed the two aggregate-as-subset cases. One single-agent
response rejected for the wrong reason (`DUPLICATE`); the others accepted the
misattribution. Critic rescued one initial rejection of an authorized revision
and introduced no additional error in this small comparison. These results do
not establish a general Critic benefit or reliable narrative checking.
See [process results](process_summary.json), [answers](process_runs.json),
[invocation references](process_invocations.json) and the
[preflight source context](input_context.json).

The original campaign `openai_grounded_revision_20261009` exhausted its declared
19 runs: 18 process runs plus one actual revision attempt. The
[manifest](../../../../configs/research/grounded_revision.execution.json) and
[suite](../../../../configs/research/grounded_revision_suite.json) were registered
before inference; the suite hash is
`1a41e54612ba49313779b7ed44b456052c28331f673e914b61d0074fa729a42c`.

## Technical recovery and reference-boundary correction

The first actual attempt hit its 4,096-output-token limit while emitting
`submit_contract_revision`, after using 3,581 reasoning tokens. The partial call
was preserved but never executed. This is recorded in
[incomplete_attempt.json](incomplete_attempt.json).

One separate technical recovery was then declared and registered under
`openai_grounded_revision_recovery_20261009`. It repeated the same authorized
parent/patch with an 8,192-token output limit. This is an additional attempt,
not a replay or a replacement result. The original campaign stayed exhausted,
and the process benchmark was not rerun. The remaining reservation allowance was
USD 1.034184; its maximum configured recovery reservation was USD 1.033296, keeping
the complete step below the existing USD 2 ceiling. The
[recovery amendment](../../../../configs/research/grounded_revision_recovery.execution.json)
records this change after the engineering failure and before the recovery call.

The recovery completed the correct revision and Critic review. Initial service
review nevertheless returned `UNKNOWN_EVIDENCE`: Critic cited two valid scoped
fact hashes alongside the source-record IDs, while that checker accepted only
record IDs. The exact proposal and critique were retained. Working revision
2.11.1 introduced deterministic policy `scoped_registry_references/1`, first
committed with architecture 2.12 in `79cbbae`. This policy resolves
only content-verified facts in the run's authorized frozen context. Unknown
hashes remain rejected. A regression reproduced the defect before the fix.

Operator reassessment used the **same recorded model outputs**, with no further
inference. `CONTRACT_REVIEW_CORRECTION` preserves the original rejection;
`CONTRACT_REVIEW_ASSESSMENT` records the new policy and result. Operator admission
also resolves Critic's advisory wording concern: inherited “all-hours” means the
registered anchors `[8,12,16]`, not all 24 clock hours. The original wording and
its provenance remain visible in [corrected_revision.json](corrected_revision.json).

## Actual development result

Design freeze was committed before calculation. The fixed 12 UTC diagnostic used
January–June 2020 development cases, retaining holidays and missing anchors.

| Measurement | Result |
| --- | ---: |
| Scheduled anchors | 130 |
| Measurable anchors | 129 |
| Missing input | 1 |
| Candidate accuracy | 48.84% (63 / 129) |
| Development-fitted baseline accuracy | 54.26% (70 / 129) |
| Candidate minus baseline | −5.43 percentage points |

The data pass the catalog's technical sufficiency rule. The negative difference
contradicts the parent's declared continuation conjecture in this development
window under its stated falsifier. This is a development comparison with a
baseline fitted in that same period; it is not independent validation, temporal
failure evidence or an economic loss measurement. No other hour was searched
after observing this result.

[development_result.json](development_result.json) is the derived export of the
catalog's authoritative commitment. [candidate_lock.json](candidate_lock.json)
locks the exact diagnostic and baseline with `NO_INDEPENDENT_WINDOW`, null economic
claim and `execution_allowed: false`. A lock does not mean the candidate passed a
predictive gate. No new validation, promotion or broker order occurred.

## Resources and verification

- 20 runs across the initial campaign and its separate recovery: 18 process runs,
  one incomplete attempt and one completed revision. **44 provider calls**.
- All returned `gpt-5.4-mini-2026-03-17`; 214,135 input and 29,003 output tokens.
- Retained reservations for this step: **USD 1.540033 / USD 2**.
- Cumulative retained reservations: **USD 26.647594 / USD 50**.
- Token-price estimate: **USD 0.29111475** for this step, ignoring cached-input
  discounts; the provider invoice has not been reconciled. See [resources.json](resources.json).
- **84 unit/API/PostgreSQL tests passed**, including v1/v2 hash preservation,
  authorized revision admission, prohibited contract changes, missing/unknown
  citations, exact fact references, lifecycle projection, isolation and replay.
- Recorded run, events, invocations and tool outputs remain identical after
  reassessment; current review annotations and operator commitments are additional
  records. Capture services were not restarted.

PostgreSQL remains authoritative. These JSON files are rebuildable exports.
Only declaration-scope correction is implemented; arbitrary contract repair,
reliable semantic validation, general researcher quality, independent temporal
evidence and executable economic value remain unverified.
