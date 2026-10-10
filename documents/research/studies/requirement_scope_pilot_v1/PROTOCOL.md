# Requirement-scope assessment: first feedback pilot

**Study:** `requirement_scope_pilot_v1` · **Design date:** 10 October 2026.
**Stage:** design freeze; execution inputs and reference review remain incomplete.
**Authority:** planning only. Human assessment/release gates remain active.

## 1. Decision and claim

This study tests whether the already reviewed requirement-scope lesson helps a
fixed Critic assess a supplied proposal. It also measures that same candidate
assessor's errors and escalation behavior. It does not generate hypotheses,
measure market returns, qualify an automated reviewer or authorize release.

The first class is `requirement_scope_consistency/1`: compare binding current or
future source requirements with the proposal's stated current diagnostic scope.
The subject action is a Research proposal; Critic produces a proposed process
finding. Findings about Critic's own errors require their own reviewed record.

The [study contract](../../../../configs/research/studies/requirement_scope_pilot_v1/study.json)
is the source of truth for fixed counts, limits, metrics and decisions. The
[design manifest](../../../../configs/research/studies/requirement_scope_pilot_v1/design.freeze.json)
binds that contract and its exact development context, lesson and model profile.
This document explains their interpretation. None is a registered execution
authorization or an assessment-class delegation.

**Reviewer choice:** the user explicitly selected a pilot with themselves as
human reference reviewer on 10 October 2026. A second independent human reviewer
has not been identified. An AI
operator can prepare cases and transcribe decisions; it cannot count as that
second human. Pilot findings remain conditional on one human reference review.
Full qualification still requires the two independent reviews and adjudication
specified in [plan 1.8](../../AGENT_LOOP_IMPLEMENTATION_PLAN.md#from-human-review-to-scoped-automation).

## 2. Frozen questions

| Track | Estimand | Use of result |
| --- | --- | --- |
| A — feedback effect | Paired change in exact process-answer correctness between `HISTORY_PLUS_REVIEWED_METHODS` and `HISTORY_ONLY`, averaged equally by case family. | Decide whether this lesson and task warrant a larger, independently reviewed study. |
| B — assessor reliability | False accusations, missed defects, component/scope/reference errors, abstention and missed escalations in the **preselected** `HISTORY_PLUS_REVIEWED_METHODS` arm. | Describe weaknesses and design the later qualification study. Never choose the better arm after reading results. |

Both tracks reuse the same scheduled outputs. They share cases, errors and
exposure; their results are not independent replications. There is one fixed
candidate, one lesson, one primary contrast and one terminal inspection. Scores
must not be used to rewrite this study's task families, prompt or success rule.

### Class boundary

- English, schema-valid `research_proposal/2` or `/3` price-only diagnostics,
  using the existing `current_diagnostic` / `future_economic` rules. A fixture
  explicitly states its contract version and provides those rules.
- Each case packet is at most 4,096 canonical UTF-8 bytes. Larger inputs are
  outside this first class. The complete serialized provider request, including
  history, lesson and tool schema, must also fit the model profile's 24,000-byte
  limit; do not truncate a case, source or instruction to make it fit.
- Assess source-scope consistency and the responsible component. Keep correct
  scope with unavailable current data separate from contradictory scope. Source
  availability cannot itself establish a process defect or economic failure.
- The test packet contains the original proposal fields and necessary rules;
  the assessor cites exact field paths. Novel payoff semantics, uncertain family
  ancestry, changed holdout permissions and trading/risk decisions require human
  escalation. They cannot receive a speculative in-class verdict.
- Invalid or disputed context also requires escalation. A correct reference
  hash verifies identity, not semantic support. No later market outcome is used
  as a process label.

Historical v1 Astra material appears only as declared development history; its
implicit binding requirements retain v1 semantics. V1 is excluded from new
in-class test cases. The study does not redefine historical proposal contracts.

## 3. Cases, independence and reference review

The design calls for **eight candidate family clusters, three cases per cluster**:
one supported scope defect, one valid near miss, and one case that must escalate.
All 24 cases receive both arms once, giving 48 scheduled assessments. The labels
describe the authoring target; only explicit human review determines whether a
candidate case actually satisfies its intended cell. Do not force a reference
label to make the allocation work.

The eight family slots are identifiers, not manufactured evidence of independence.
The operator must propose different scope mechanisms and document each family's
relationship to earlier suites and to the other families. Changing a source name,
sentence wording, case ID or decision hour cannot create a new family. Reviewers
merge related families and record uncertain ancestry. If eight eligible clusters
cannot be supported, preparation stops as `INSUFFICIENT_FAMILY_DIVERSITY`; a
smaller descriptive exercise requires a new explicit design. No test run begins
merely because 24 JSON objects exist.

The six reviewed historical assessments and earlier requirement/grounding suites
are development/regression material. Test families may not be paraphrases of
those templates. These new tasks would be **operator-authored synthetic process
cases**, with that provenance retained. Even accepted family separation does not
establish statistical independence or generalization to naturally occurring
research proposals, other languages, other models or economic decisions.

### Preparation sequence

1. Finish the read-only study harness and scorer against **development** fixtures.
   Freeze their code, instructions and output-schema hashes before exposing the
   candidate system to any test case or human test answer.
2. An operator prepares candidate family dossiers and case packets, recording
   author, construction rationale and exposure. The case author and future
   assessor's shared provider/model ancestry is declared. The evaluating agent
   does not write its references. No pilot test packets or answers have been
   authored as part of this design freeze.
3. A human reads each original case and its rules before seeing the author's
   suggested label. Record field-level references, status, component, severity,
   route and acceptable rationale. Adjudicate disputes before execution. An
   unresolved semantic reference becomes an escalation case only when its
   ambiguity itself is explicitly reviewed; otherwise the case is ineligible.
4. Freeze the full reviewed 24-case inventory and human references, then the
   execution manifest, before the first probe or scored provider call. Case
   replacement after outcomes is prohibited. Pre-execution rejection and revision
   of candidate cases remains visible in the preparation ledger.

### Access and exposure

Reference labels, family authoring notes and expected answers belong in an
operator-only store. The current broadly worker-readable `research.artifacts`
table must not hold unreleased references. A Git-ignored path alone does not
provide isolation. The executor receives only the approved case packet; the
scorer/reviewer receives references under a different identity. The preparation
record must include denial checks covering tools, mounts, logs and error output.
Opaque runtime case IDs must not reveal strata, labels or family slot names.

Reference access for preparation is declared operator exposure. Once candidate
answers or scores influence changes to the candidate system, the relevant test
families are consumed for future tuning. Masking dates or starting a fresh chat
does not restore that independence. Future qualification needs fresh families
and real shadow cases; this pilot cannot be reused as untouched qualification.

## 4. Matched inputs and execution

Both arms receive the same versioned class instructions, proposal, applicable
rules and [development history](../../../../configs/research/studies/requirement_scope_pilot_v1/history.json).
The history is an explicit projection of the three original proposals and
critiques, with their source hashes and historical contract semantics. It omits
the later human process findings. The treatment adds exactly the frozen
[released method lesson](../../../../configs/research/studies/requirement_scope_pilot_v1/method_feedback.json),
including its applicability and counterexamples. Its source integrity and current
release eligibility must be checked again before execution.

The subject model is the existing user-selected `gpt-5.4-mini`, medium reasoning,
bound to the [pilot profile](../../../../configs/research/studies/requirement_scope_pilot_v1/model.profile.json).
Keep profile, system instruction, tools, history, per-call limits and scorer
identical across arms. The extra lesson is the intended intervention; report the
extra input cost rather than padding the control with arbitrary text.

Run each pair in fresh isolated contexts close together. Use the frozen case
order and alternate which arm goes first. Do not let either arm see the other's
answer or any test reference. Record returned model identity and invocation
lineage. Unexpected identity changes or observed provider-behavior drift stop
the study; they cannot silently create a pooled multi-version result.

Each scheduled arm has one typed-capability probe and at most one assessment
call. Probe failure leaves that assessment missing in the scheduled denominator.
No retries, extra deliberation, best-of selection or post-failure recovery are
allowed inside this design. Cached or repeated transport delivery may not create
another provider attempt. Each real dispatch consumes the corresponding budget.

## 5. Answer and scoring contract

The future pilot answer records one `REQUIREMENT_SCOPE_CONFUSION` finding using
the existing finding fields (status, component, severity, references,
applicability, explanation), plus a proposed route (`ASSESSABLE` or `ESCALATE`)
and escalation reason. `ASSESSABLE` means the case fits the test class; it grants
no actual automatic assessment or release permission. The answer is an evaluation
artifact and cannot be passed directly to `assess-process` as a reviewed decision.

For each case, score these dimensions separately against the frozen reference:

- Correct defect status; correct component and severity.
- Citation existence and whether cited text supports the asserted scope.
- Correct route, including a specific reason for mandatory escalation.
- Rationale consistency: it must distinguish scope inconsistency from missing
  data, respect historical contract semantics, and avoid unsupported payoff or
  broad agent-capability claims. Exact wording is not required.

An exact process answer passes only when every required dimension passes. The
human checks semantic rationale against the frozen acceptance rules with arm
identity hidden and output order fixed before grading. Preserve uncertainty and
any guessed arm identity; hiding the label does not prove blinding. The scorer
must not grade the treatment by checking whether it repeats the lesson's words.
Post-output discoveries of defective references invalidate the affected case;
they do not permit a favorable replacement or an adjusted success threshold.

For completion-inclusive accuracy, a failed or missing answer contributes zero
on a valid-reference scheduled case, while its technical failure remains a
separate category, not a supported agent defect. An invalid reference removes
that case from both arms' semantic denominators and makes the full pilot
inconclusive. Publish retained paired support explicitly; do not compare arms
over different surviving cases. In-class abstention counts as a missed decision
and reduced coverage; escalation is correct on a mandatory-escalation case.

Report all scheduled rows, raw counts per stratum, per-family paired deltas,
macro-average accuracy, completion, citations, source/component errors, observed
cost and conservative reservations. Report Research/author defects separately
from checker/context defects. No market outcome, high pass rate or harmless
refusal can substitute for the registered process target.

### Pilot decision rule

The frozen numerical rules are in `study.json`. A `PROMISING_FOR_LARGER_STUDY`
result requires the complete valid reviewed inventory and all scheduled outputs,
at least a 0.125 increase in family-macro exact accuracy, at least 14/16 correctly
handled in-class treatment cases, zero false accusations on the eight valid
near misses, no more than one missed supported defect, and correct escalation of
all eight mandatory-escalation cases. All source/authority safety checks must pass.

These are engineering screening thresholds selected before inference. With only
eight authored clusters, report paired family results descriptively; no
confirmatory significance, generalization interval or automated-authority claim
is permitted. A failed metric yields `NOT_PROMISING_UNDER_REGISTERED_RULE`; a
missing or invalid reference/output or early stop yields `INCONCLUSIVE`.
Record the measured dimensions even when the overall result is inconclusive.
If history-only already performs perfectly, the effect gate cannot pass; retain
that ceiling result rather than inventing a harder post-hoc test.

Track B reports reliability separately, even if Track A improves. Its pilot
measurements cannot satisfy the later class-specific upper error bounds or
real-world shadow requirements. No pilot result grants `AUTO_ASSESS` or
`AUTO_RELEASE_METHOD`.

## 6. Budget and stopping

At most 48 scheduled assessments and 96 provider invocations are planned.
The proposed step ceiling is **USD 3**, within the existing aggregate USD 50
authorization, subject to checking every intervening reservation. This design
phase spends **USD 0** on providers and allocates no campaign funds.

The copied tariff is the project's **09 October 2026 recorded pricing basis**,
not a fresh price verification. At that tariff the conservative worst-case
reservation is USD 2.907648, including framing and maximum output for every
probe and assessment. Before execution, verify current official prices and the
aggregate ledger; if rates or remaining allowance invalidate the ceiling, stop
and revise the design before any calls. The USD 50 ceiling is never reset.

Stop at the first exhausted run/token/dollar/time limit, exposure leak, invalid
source, authority violation or model-binding change. Pair scheduling is fixed;
budget pressure cannot select easier cases. Preserve unfinished scheduled rows.
Inspect aggregate performance once after termination; do not add cases because
the result is negative, close or statistically unconvincing. New work needs a
linked design, separate budget and an exposure-aware case allocation.

## 7. Readiness and the next implementation

The design manifest freezes the **study design and existing inputs only**. It does
not claim that test cases, independent references or a compatible runner exist.
The [readiness record](../../../../configs/research/studies/requirement_scope_pilot_v1/readiness.json)
lists those open gates. It is a derived preparation checklist, not authority.

The existing `ProcessRunner` uses admissibility answers, legacy feedback selectors
and mutable registry grounding; its scorer checks disposition/reason and cannot
score this class's attribution, semantic rationale or escalation dimensions.
The next implementation therefore needs:

1. A bounded study answer contract, immutable input binding and paired scheduling
   with idempotent dispatch accounting; preserve the existing historical runner.
2. Reference isolation and a blinded human scoring workflow with immutable
   per-dimension grades and explicit uncertainty/invalidity.
3. A deterministic report over every scheduled case, implementing this design's
   metric denominators and terminal decision without writing market evidence,
   reviewed process assessments or released lessons.
4. Focused tests for reference leakage, arm contamination, missing/failed runs,
   wrong attribution, abstention, revoked lesson eligibility and exhausted budgets.

Only after those checks, case/reference review and a final execution manifest
may the bounded provider run begin. The production human gate remains unchanged
throughout this pilot. A later qualification study requires its own fresh
reference families, two independent human reviews, inferential support, shadow
period, audited release pipeline and explicit class activation.
