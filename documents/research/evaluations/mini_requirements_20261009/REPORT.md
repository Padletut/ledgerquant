# Scoped requirements: Mini execution record

**Date:** 09 October 2026. **Mode:** exposed contract regression and retrospective
research engineering. Architecture 2.10.2; proposal/critique contract v2.

## Frozen scope and execution

The approved step used campaign `openai_mini_requirements_20261009`: 24 process
runs followed by one research proposal, with a shared USD 2 reservation ceiling
inside the existing USD 50 authorization. Its parent campaign remains exhausted
at 40 runs and USD 24.187702 in retained reservations. The new campaign stopped
at its 25-run limit, despite unused money and invocation capacity.

The [execution manifest](../../../../configs/research/mini_requirements.execution.json)
and [reference suite](../../../../configs/research/contract_requirements_suite.json)
were frozen and stored as immutable operator artifacts before Mini inference:

- Manifest: `cd9f76e359f3c6e4c986466ac549477b6d71def5d484b714e75c6ee38219c376`.
- Suite: `51efd91690e4106e0ecabf90eaebf0d2cdec6e44398cac6eed12c54f2d65678e`.

All 49 calls requested `gpt-5.4-mini` and returned
`gpt-5.4-mini-2026-03-17`. The 17 model runs each passed a typed capability probe.
All calls completed with recorded usage. This demonstrates the exercised
function-calling path, not factual accuracy, calibrated confidence or immutable
provider weights. The checklist's eight runs made no model call.

## Process results

Four exposed contract templates each ran twice in three arms, with structured
feedback fixed. The templates cover deferred economic costs, current unavailable
news, contradictory current cost requirements and exact duplicate identity.
Reference labels were authored before inference and excluded from model inputs.
No-feedback comparison was deferred; the invalidated original comparison stays
invalid. No prompt or label was changed after these outcomes.

| Arm | Correct / planned | Failed or missing runs | Reserved USD |
| --- | ---: | ---: | ---: |
| Single agent | 8 / 8 | 0 | 0.231606 |
| Research + Critic | 7 / 8 | 0 | 0.383191 |
| Fixed checklist | 8 / 8 | 0 | 0 |

Critic corrected one initial rejection of a properly deferred cost requirement.
In another repetition, it changed a correct `BLOCKED_DATA_REQUIREMENT` response
into `REJECT`: it interpreted a current missing-news requirement as contradictory
deferral, despite the explicit current scope and registered blocking rule. The
incorrect final answer expressed 0.91 confidence. It remains a process error,
not evidence that the underlying economic idea failed.

The four related templates and repeated runs do not provide independent evidence
of general researcher quality. These descriptive results do not establish a
Critic benefit or justify calibrated use of reported confidence. The checklist
does not understand arbitrary narrative contradictions. See
[process_summary.json](process_summary.json), [process_runs.json](process_runs.json)
and [exact invocation references](process_invocations.json).

## One actual proposal: rejected duplicate

Run `23632117-fb7e-40c6-bffc-b9bbc39df16e` used nine calls: one probe, four Research
calls and four fresh-context Critic calls. It recorded 27,822 input and 5,894
output tokens, with USD 0.305062 reserved.

Research proposed the existing prior-hour momentum rule at 12 UTC with a
four-hour target. Broker costs were correctly scoped `future_economic`; Critic
explicitly confirmed narrative/field consistency. The v1 cost-scope problem was
therefore absent in this draft.

However, the normalized diagnostic exactly matches the earlier blocked draft
`e7f85e02-fe52-473b-a786-6e659ae2f246`. Its signature remains
`24c3c3e2b3d52116469ac293d2be78ea9778a0a5cb3cb0628825b04c701e36b5`.
The task and source-coverage tool exposed this prior attempt. Critic recommended
`REVIEW` and missed the duplicate; the contract service correctly returned
`REJECTED / DUPLICATE`. Operator review appended a rejection. The new draft and
the old blocked draft remain separate attempts in the same exposed family.

The new proposal also used the released aggregate 2020 result as support for
"the same diagnostic" without establishing a measured 12 UTC subset result.
That attribution does not establish subset performance. Its falsifier mixed
predictive performance with administrative admissibility. Both are limitations
of this proposal, not evaluator measurements.

There was **no design freeze, new development calculation, candidate lock or
validation**. No replacement proposal was sampled after rejection. The operator
decision, exact proposal, critique and invocation references are in
[discovery_run.json](discovery_run.json). Recorded-output replay matched the
original run exactly and added no provider calls. The two original historical
windows remain `CONSUMED`.

## Resources and verification

- 25 runs, 49 provider calls; 99,499 input and 23,678 output tokens.
- New retained reservations: **USD 0.919859 / USD 2**.
- Cumulative retained reservations: **USD 25.107561 / USD 50**.
- Token-price estimate for this step: **USD 0.18117525**. This ignores cached-input
  discounts and is not a reconciled invoice. See [resources.json](resources.json).
- **69 tests passed** across unit/API checks and a migrated disposable PostgreSQL
  database. Tests cover v1 hash preservation, explicit v2 schemas, scope gating,
  narrative-objection admission, rejection paths, replay and maximum budget bounds.
- Only one-shot research images were rebuilt; the capture stack was not restarted.

These JSON files are derived exports. PostgreSQL remains authoritative for
artifacts, invocation history, operator decisions and reservations.

## Remaining work

Mini's tested API capability is usable, but the agent workflow still needs stronger
use of prior attempts and evidence attribution. A further bounded evaluation should
measure duplicate avoidance on real proposals, distinguish aggregate from subset
claims and separate predictive falsifiers from administrative eligibility. Freeze
its cases, budget and stopping rule before running it; do not relax the duplicate
gate to make this proposal pass. Broader researcher quality, semantic contradiction
recall, no-feedback benefit, economic payoff and new independent validation remain
unmeasured. This step does not authorize broader search or trading.

## Subsequent interpretation correction — 09 October 2026

The original `REJECTED / DUPLICATE` output records the then-active v2 policy. The user clarified that identical market-idea identity does not by itself justify rejecting an authorized corrected contract revision. Operator review annotates this attempt as `SAME_IDEA_REVISION_CANDIDATE`; its original rejection, unlinked submission and narrative defects remain recorded. A later attempt needs an explicit parent and verified patch.

The append-only [correction records](../grounded_revision_20261009/review_corrections.json)
preserve original hashes, family accounting and consumed exposure. They grant no
retroactive admission. The new v3 contract separates idea identity from attempt
identity and applies an authorized scope correction on the service side.
