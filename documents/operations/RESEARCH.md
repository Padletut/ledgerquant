# Bounded research-agent operations

**Implemented:** 09 October 2026; v3 implementation described in [architecture 2.12](../ARCHITECTURE.md). Its intermediate working revision was 2.11.1, consolidated into 2.12 in commit `79cbbae`. Architecture 2.13 (10 October 2026) adds the repair exposure gate described below; the feedback-type and process-assessment contracts remain planned.

The one-shot workflow is Research proposal → fresh-context Critic → deterministic
contract review. An operator can then reject or admit an eligible draft to a
design freeze, fixed-catalog development calculation and candidate lock. There
is no automatic economic evaluation, promotion or trading. The [execution
record](../research/evaluations/agent_loop_bootstrap_20261009/REPORT.md) contains
the first real run and the small process comparison.

## Ownership and files

| Location | Responsibility |
| --- | --- |
| `src/ledgerquant/research/` | Catalog, proposals, registry, import, operator admission and process scoring |
| `src/ledgerquant/agents/` | Immutable instructions, scoped tools and bounded orchestration |
| `src/ledgerquant/models/` | Provider-neutral generation contract and resource reservation |
| `src/ledgerquant/integrations/model_providers/openai.py` | OpenAI Responses transport |
| `configs/research/` | Actual profile, campaign budget, initial task and frozen process suite |
| `deploy/compose.research.yaml` | Optional operator/worker jobs alongside the capture stack |
| `data/research_control/operator/` | Local import bundle and operator commands; never mounted in the worker |
| `data/research_control/worker/` | Local registration IDs and permitted task/config inputs |
| PostgreSQL `research` schema | Authoritative identities, exact hashed artifacts, calls and append-only events |

The local `data/` and `credentials/` directories are ignored by Git. PostgreSQL
and its existing volume hold the durable registry. Local JSON reports are
rebuildable exports, not an alternative authority. Back up the PostgreSQL volume
with the capture storage; deleting it also deletes the research ledger.

## Current configuration

The current user-selected model is **`gpt-5.4-mini`**, with medium reasoning.
Its profile is `configs/research/openai_gpt54_mini.profile.json`. Compose mounts
that single source at `/run/config/model-profile.json` and sets
`MODEL_PROFILE_FILE` for both worker and operator jobs. `--profile` explicitly
overrides it; outside Compose, either that option or `MODEL_PROFILE_FILE` is
required. Registration and inference must use the same immutable profile.

Standard prices checked on 09 October 2026 are USD 0.75/M input tokens and
USD 4.50/M output tokens. Cached input is USD 0.075/M; reservations conservatively
charge all input at the ordinary input price.
[Official OpenAI model specification](https://developers.openai.com/api/docs/models/gpt-5.4-mini)

The original Astra profile and **USD 50 total** initial campaign policy remain
in `configs/research/openai_astra_bootstrap.*.json` for historical identity and
replay. The campaign is exhausted at 40 runs; changing models does not reopen it
or create another USD 50 allowance. Mini's Research/Critic versions are registered
under that existing campaign without starting inference. Their local registration
file is `data/research_control/worker/registration-mini.json`. That registration records the historical v1 binding. New v2 executions use the
separately bounded campaign described below; each model run starts with a typed
capability probe. Research quality remains separate from API conformance.

Every provider attempt reserves
its input-byte upper estimate, framing allowance and maximum output tokens before
dispatch. Reservations use the higher standard input/cache-write rate. Completed
and unknown calls keep their reservation; there is no automatic refund or retry.
This deliberately stops earlier than a policy that spends the full estimated
invoice. Provider usage and invoices remain the billing authority.

The credential file is `credentials/openai-api.key`, containing only the API
key. The restricted database login uses `credentials/research-worker.pwd`.
Secrets are mounted separately and never recorded as model input. Hosted weights
can change under an alias; the returned model name and a per-run typed capability
probe are recorded, but neither proves identical weights or research quality.
[Historical Astra specification and pricing](https://developers.openai.com/api/docs/models/gpt-6-astra)
and [Responses function calling](https://developers.openai.com/api/docs/guides/function-calling)
were checked before the first call.

The worker receives released 2020/2021 evidence and a bounded page of the
January–June 2020 development snapshot. It cannot mount the raw tick archive,
read `market` tables, insert measured evidence or write operator commitments.
The current research schema contains **released evidence only**. A future sealed
validation store needs separate access control before unreleased outcomes are
introduced; putting them into today's generally readable research artifacts
would break the boundary.

## Reproduce the original bootstrap

From the repository root, build and migrate without restarting capture:

```bash
docker compose -f deploy/compose.yaml -f deploy/compose.research.yaml build research-worker research-operator migrate
docker compose -f deploy/compose.yaml run --rm --no-deps migrate
```

Create the operator/worker control directories, generate a strong worker password
in its secret file and copy the selected versioned profile, policy and task into
the corresponding control directories. Export the verified legacy bundle:

```bash
PYTHONPATH=src .venv/bin/python -m ledgerquant.research.agent_cli export-legacy --root . > data/research_control/operator/legacy-bundle.json
docker compose -f deploy/compose.yaml -f deploy/compose.research.yaml run --rm --no-deps research-operator provision-worker --password-file /run/secrets/research_worker_password
docker compose -f deploy/compose.yaml -f deploy/compose.research.yaml run --rm --no-deps research-operator register --bundle /control/legacy-bundle.json --profile /control/openai_astra_bootstrap.profile.json --policy /control/openai_astra_bootstrap.policy.json --campaign openai_astra_bootstrap_20261009 --contract-version 1 > data/research_control/worker/registration.json
```

The first command key is retained permanently:

```bash
docker compose -f deploy/compose.yaml -f deploy/compose.research.yaml run --rm --no-deps research-worker run --config /control/registration.json --profile /control/openai_astra_bootstrap.profile.json --task /control/first_agent_loop.task.json --command-key astra-first-loop-20261009-01
```

With unchanged registered bindings, delivering that command again returns stored
results and makes no provider call. A changed task or version cannot reuse the
key. Fresh inference needs a new key and consumes a new attempt. Re-register
changed instructions/tools/profile as a new effective agent version; never
silently substitute another model. Keep retries within the original campaign so
the authorized total does not reset.

To reproduce the historical Mini v1 binding, register using the mounted default
profile (omit `--profile`) and a separate output file:

```bash
docker compose -f deploy/compose.yaml -f deploy/compose.research.yaml run --rm --no-deps research-operator register --bundle /control/legacy-bundle.json --policy /control/openai_astra_bootstrap.policy.json --campaign openai_astra_bootstrap_20261009 --contract-version 1 > data/research_control/worker/registration-mini.json
```

This only registers versions. A future task must have an explicitly allocated
campaign allowance and use a registration matching the Mini profile. A stale
Astra registration fails the version check rather than silently switching models.

To replay irrespective of the current code's active bindings:

```bash
docker compose -f deploy/compose.yaml -f deploy/compose.research.yaml run --rm --no-deps research-worker replay --run-id e7f85e02-fe52-473b-a786-6e659ae2f246
```

Replay returns recorded requests, responses and ordered tool results. It does
not execute tools, regenerate a proposal or claim fresh inference. A reserved
invocation without a completion remains visibly unknown after a crash; command
redelivery does not dispatch it again. Investigate it before creating a new
attempt. Refusals, malformed output and timeouts are engineering outcomes, not
measured economic failures.

## Operator admission and corrections

`admit --decision /control/decision.json` is an operator command using the
`Admission` schema in `research/admission.py`. It requires the exact draft ID and
hash, actor, `ADMIT_DEVELOPMENT` or `REJECT`, reason and explicit resolutions for
every material/blocking Critic objection. The worker database role cannot execute
the resulting writes. A Critic `REVIEW` recommendation is never approval.

Only an admissible typed contract can be frozen. V2/v3 requirements declare `current_diagnostic` or
`future_economic` scope. The former blocks on unavailable data; the latter records
a prerequisite for a future economic contract. Current broker costs contradict
the price-only catalog: v2 rejects the contract, while v3 reports
`BLOCKED_CONTRACT_DEFECT`. Critic must explicitly check
narrative/field consistency and record a material objection if contradictory;
operator admission requires an explicit resolution. Semantic checking remains
fallible and is not replaced by keyword matching.

Historical registrations use `--contract-version 1`. Their required-source
entries remain binding regardless of prose. The first real draft retains its
broker-cost conflict and blocked state. Do not rewrite it or normalize it to v2.

An admitted design is committed before development begins. The catalog retains
missing anchors and recalculates the majority baseline on the selected hour
subset. The candidate lock records that exact baseline and calculation hash.
Current locks end with `NO_INDEPENDENT_WINDOW` or `INSUFFICIENT_SUPPORT`; neither
authorizes trading. Repeating the same operator command is idempotent.

`invalidate --evidence-id ID --actor ACTOR --reason TEXT` appends a correction
event. It preserves the old evidence and consumed windows, excludes that evidence
from future support, blocks dependent admission and marks dependent run reports
`REVIEW_REQUIRED`. Recorded historical contexts remain unchanged.

## Process evaluation and limits

The initial campaign has reached its frozen **40-run limit**. Replays remain
available; fresh inference needs a separately reviewed campaign allowance. Do
not edit the old policy to continue searching. Its first 36-run process
comparison is invalid because of an ambiguous duplicate context; the repaired
context passed three corrective checks. The full original none/structured comparison remains
unmeasured. The new requirement regression below is a separately frozen test.

`configs/research/contract_process_suite.json` freezes three synthetic contract
templates, two repetitions, three arms and two feedback policies: 36 runs.
`research/process_evaluation.py:schedule` produces worker tasks without reference
labels. Register `--workflow process_review` under the **same campaign**, then
run `process-suite --config ... --profile ... --tasks ...`. The scorer consumes
the operator's frozen suite and compact recorded reports; missing/failed runs
remain in the denominator.

Reference labels come from a developer-authored rubric, not a model judge or
market outcome. The fixed checklist answers the same narrow contract question.
Audit cases are withheld from the provider until their runs, but all three
templates share the same small catalog. Repetitions do not become independent
research families. Reports therefore give descriptive task means and explicitly
withhold generalization/significance claims. They do not measure unrestricted
discovery, semantic/news reasoning or whether a rejected idea would earn money.

Unit/API checks run with `.venv/bin/python -m pytest tests/unit tests/contract`.
PostgreSQL integration tests require `RESEARCH_TEST_DATABASE_URL` naming the
disposable database `research_test`. They reset that test ledger and must never
be pointed at the capture database.

## Approved Mini requirement regression

`configs/research/mini_requirements.execution.json` freezes the additional step:
24 process runs and one discovery run, at most 53 provider calls and USD 2 in
retained reservations. The prior USD 24.187702 stays charged; combined reservations
cannot exceed USD 26.187702 under this allocation, within the original USD 50.
The parent campaign remains exhausted. Both v2 registrations share campaign
`openai_mini_requirements_20261009`; do not create separate budgets for the arms.

The process profile explicitly reduces maximum output to 1,536 tokens and request
size to 18,000 bytes. The ordinary Mini profile remains the discovery binding.
With 40 process calls and up to 13 discovery calls, even the maximum request/output
reservations sum to USD 1.998912. The deterministic checklist has the same per-run
allowance but makes no model call. Actual usage, retained reservations and the
provider invoice are different quantities.

The frozen suite is `configs/research/contract_requirements_suite.json`:
deferred costs, current missing news, contradictory current costs and an exact
renamed duplicate; two repetitions and three arms. Structured feedback is fixed.
All templates are exposed contract regressions, not a held-out research benchmark.
No-feedback comparison, broad semantic error detection and economic false rejection
remain unmeasured. Reference labels never enter provider contexts.

Register the process binding with `--workflow process_review --contract-version 2`
and its explicit process profile; register discovery with `--contract-version 2`
and the mounted ordinary Mini profile. Both use `mini_requirements.policy.json`.
Use separate registration output files. Generate tasks with the existing
`process_evaluation.schedule` function; only operator inputs contain the rubric.
The suite and execution manifest are immutable registry artifacts as well as
version-controlled inputs. Do not increase the budget or resample failures after
seeing results. Run the single `mini_requirements.task.json` only once, retaining
its parent campaign and blocked-draft references. Operator review remains required
before development, and no independent validation window is allocated.

This campaign has now completed and is exhausted at 25 runs. Its 49 provider calls
returned `gpt-5.4-mini-2026-03-17`; the step retained USD 0.919859 in reservations.
The actual proposal was rejected as a duplicate, so no development or candidate
lock occurred. See the [Mini execution record](../research/evaluations/mini_requirements_20261009/REPORT.md).
Replays remain available. Further inference needs a new explicitly allocated
step; unused money does not reopen this campaign's stopping rule.

## Grounded contracts and corrected attempts (v3)

New registrations default to `--contract-version 3`; old v1/v2 registrations and
replays remain explicit. Research and Critic share an immutable `GROUNDING_CONTEXT`
record. Source-coverage results include all prior signatures and authorized
revision parents; released-evidence results include exact, scoped fact references.
Both successful and negative released outcomes must be cited. The service rejects
unknown facts, missing prior comparisons and aggregate-as-subset attribution.
It does not certify arbitrary narrative claims.

Same market idea does not mean same attempt. An operator can authorize a parent
ID/hash and a scope-only correction through `revision_authorizations` in the
frozen task. The agent uses `submit_contract_revision`; the service copies the
parent's contract and applies only the authorized `broker_costs` scope change.
A `revision_only` task cannot submit a different hypothesis. Each revision has a
new run/draft ID and keeps its parent, family and consumed-window exposure.
Operator admission can freeze and develop an eligible revision; a repeated idea
without a valid revision link cannot claim newness. Decision/payoff changes need
a separately reviewed hypothesis path. The implemented correction is deliberately
limited to the observed cost-declaration defect.

`correct-contract-review --decision /control/FILE.json` appends an operator-only
annotation with exact draft and original-review hashes. It preserves the original
output, consumes no new holdout and grants no admission. Annotated run reports
show `REVIEW_REQUIRED` and the explanation. The first two attempts now carry the
user-requested interpretation corrections in
`configs/research/grounded_revisions.corrections.json`.

Campaign `openai_grounded_revision_20261009` is limited to 19 runs and 41 calls,
with a shared USD 2 ceiling: 18 process runs and one actual revision. It uses the
explicit process profile `openai_mini_grounding_process.profile.json` (32,000
request bytes, 2,048 output tokens) and revision profile
`openai_mini_revision.profile.json` (five tool steps per role). The worst-case
reservation is USD 1.985184. Prior reservations remain USD 25.107561, so this
allocation stays within the original USD 50 authorization. Unused money does not
extend the run limit. V3 process testing currently supports structured feedback
only, using scoped facts; no-feedback comparison remains pending.

The initial 19-run campaign is now exhausted. One separate engineering recovery,
`openai_grounded_revision_recovery_20261009`, was declared after output truncation
before submission. Its explicit profile raises output capacity to 8,192 tokens
and limits request size to 72,000 bytes. Its reservation ceiling is USD 1.034184,
from the remaining allowance of the same USD 2 step. It is also exhausted at one
run. Original failures and calls remain counted; this is not automatic retry.

The completed draft was initially rejected because Critic cited valid fact hashes
where the checker recognized only source-record IDs. Policy
`scoped_registry_references/1` now resolves exact, verified in-context facts as
Critic references and continues rejecting unknown hashes. The original review
is preserved with a `CITATION_NAMESPACE_DEFECT` annotation. Operator admission
records a separate `CONTRACT_REVIEW_ASSESSMENT` using the unchanged proposal and
critique; no additional model call is needed for deterministic reassessment.

The corrected attempt was admitted and developed: 129 measurable anchors out of
130, candidate accuracy 48.84% versus baseline 54.26%. Its candidate lock has
`NO_INDEPENDENT_WINDOW`, no economic claim and no execution permission. Later
prior-inventory views show operator/lock state alongside the original review
and immutable commitment references. The entire step reserved USD 1.540033.
See the [full execution record](../research/evaluations/grounded_revision_20261009/REPORT.md).

## Repair exposure gate (architecture 2.13)

A v3 task that carries `revision_authorizations` must also declare
`repair_policy`. `premeasurement_repair` is the strict route: the service must
establish that no relevant development or validation outcome was exposed.
`exposed_corrected_attempt` is the route the historical correction used: the
attempt proceeds, and its exposure state is recorded so it can never be
described as an unexposed repair. A task with authorizations but no policy, or
a policy without authorizations, stops before inference. The strict route also
requires `submission_policy: "revision_only"`.

Each authorization needs three further fields beyond the parent ID/hash, patch
and reason:

```json
{
  "parent_draft_id": "e7f85e02-fe52-473b-a786-6e659ae2f246",
  "parent_draft_sha256": "a09b3f29fc094bf0eb810a9953d9756f6bb428282b0c71c1b2495f89d144f034",
  "scope_changes": [{"requirement_index": 0, "scope": "future_economic"}],
  "reason": "Cost-scope-only correction with unchanged exposure.",
  "defect_reference": {"kind": "CONTRACT_REVIEW_CORRECTION",
                       "sha256": "132e3358e814560d845fa4f83453d929e5d33b1398fe0bad5e30747877f9aa04",
                       "classification": "BLOCKED_CONTRACT_DEFECT"},
  "reviewer": "operator_name",
  "reviewer_outcome_exposure": "EXPOSED"
}
```

`defect_reference` must resolve to the parent's recorded
`CONTRACT_REVIEW_CORRECTION` commitment, or to its `CONTRACT_REVIEW` event when
the service itself returned `BLOCKED_CONTRACT_DEFECT`; any other hash or
classification stops the run with `DEFECT_REFERENCE_INVALID`.
`reviewer_outcome_exposure` is the operator's own declaration
(`NONE_DECLARED`, `EXPOSED` or `UNKNOWN`); the registry cannot verify what a
person has read, and a declared exposure is never cleared by an empty scan.
The example above shows the only truthful declaration for the historical
12 UTC parent, whose family is exposed for every catalog hour subset.

When the run's `GROUNDING_CONTEXT` (`research_grounding/2`) is frozen, the
service records a `repair_exposure/1` assessment under each revision parent:
released evidence whose declared hours overlap the repaired diagnostic,
development results and candidate locks for overlapping family drafts, and
labelled development pages read by the parent run, same-idea attempts,
`related_attempt_ids` and the current run, for both roles. Overlap or a declared
exposure is `EXPOSED`; a missing participant or unparseable record is
`UNKNOWN`; only an empty overlap is `NONE_ESTABLISHED`. Agents see the
decision through `read_source_coverage` but cannot change it.

A strict run whose assessment is not `NONE_ESTABLISHED` records the context,
then stops with a `STOPPED` event of kind `REPAIR_EXPOSURE_DENIED` before any
provider call. The run still counts against the campaign; redelivering the
command returns the same record. In an eligible strict run neither role is
offered `read_development_snapshot`; an attempted call is recorded with
`OUTCOME_READ_PROHIBITED`, and submission requires only the source-coverage and
released-evidence reads. The tool policy is taken from the frozen grounding
context, so the task field alone never relaxes a v1/v2 run's read requirement.

`admit` on an authorized revision recomputes the findings at that moment and
appends `REPAIR_ELIGIBILITY_RECHECK` to the draft. If a strict repair has
acquired intervening exposure, for example a development result for an
overlapping hour subset, the command fails with `REPAIR_EXPOSURE_DENIED` after
the denial has been committed; repeating the command denies again, no design
freeze or operator decision is written, and `REJECT` remains available. On the
exposed route the recheck records the current exposure and admission proceeds.
The design freeze carries the recheck decision, exposure and hash.

The historical correction `d6149cdb-bc86-47bb-8857-d0225010c35e` was frozen
under `research_grounding/1` and is not reassessed. Its admission, lock and
development result are unchanged, and it is not an outcome-unexposed repair.
Fixture-only tests exercise the eligible path with evidence declared on
non-overlapping hours; no real run has done so.
