# Bounded research-agent operations

**Implemented:** 09 October 2026, architecture 2.10.1.

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
file is `data/research_control/worker/registration-mini.json`. The mandatory
capability probe will run before any future agent workflow; Mini's real API
behavior and research quality have not yet been measured in this project.

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
docker compose -f deploy/compose.yaml -f deploy/compose.research.yaml run --rm --no-deps research-operator register --bundle /control/legacy-bundle.json --profile /control/openai_astra_bootstrap.profile.json --policy /control/openai_astra_bootstrap.policy.json --campaign openai_astra_bootstrap_20261009 > data/research_control/worker/registration.json
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

For the new Mini binding, register using the mounted default profile (omit
`--profile`) and a separate output file:

```bash
docker compose -f deploy/compose.yaml -f deploy/compose.research.yaml run --rm --no-deps research-operator register --bundle /control/legacy-bundle.json --policy /control/openai_astra_bootstrap.policy.json --campaign openai_astra_bootstrap_20261009 > data/research_control/worker/registration-mini.json
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

Only an admissible typed contract can be frozen. Required sources are binding:
a sentence saying a source is optional cannot cancel an entry in
`data_requirements`. The first real draft has precisely this conflict over
broker costs and remains blocked. Do not edit its recorded payload to unblock it.

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
context passed three corrective checks. The full corrected comparison remains
unmeasured.

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
