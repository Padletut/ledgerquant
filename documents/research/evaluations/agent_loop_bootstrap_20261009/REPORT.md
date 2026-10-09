# First bounded agent loop and process checks

**Date:** 09 October 2026. **Mode:** retrospective engineering research.

## Actual Research/Critic execution

| Field | Recorded value |
| --- | --- |
| Campaign | `openai_astra_bootstrap_20261009` |
| First run | `e7f85e02-fe52-473b-a786-6e659ae2f246` |
| Requested/returned model | `gpt-6-astra` |
| Calls | 9: typed capability probe, four Research calls, four Critic calls |
| Input/output tokens | 20,902 / 1,684 |
| Proposal | EURUSD, prior-hour momentum, 12:00 UTC, four-hour target |
| Critic recommendation | `REVIEW`; advisory temporal-instability objection |
| Contract decision | `BLOCKED_DATA_REQUIREMENT` |
| New development/validation | None |

[first_run.json](first_run.json) preserves the proposal, critique, decision,
version identities and exact invocation artifact references. PostgreSQL remains
the authority; this file is a derived export. Recorded-output replay reproduced
the requests, responses and tool results without another provider invocation.

The proposal described broker costs as relevant only to a future economic
extension but included `broker_costs` in its required-data field. Critic agreed
with the narrative and missed that structural contradiction. The contract
service treated the typed declaration as binding and blocked admission. This
is an unadmitted proposal with a conflicting data requirement, not evidence that
the price idea lacks value and not a measured `COST_FAILURE`.

Both earlier hypotheses were imported by their existing hashes. The original
2020 predictive pass and 2021 temporal failure remain unchanged, including each
file's original one-trial count. The family retains both consumed historical
validation windows. No new untouched holdout or economic result was created.

## Process comparison: invalidated, then repaired

The frozen suite scheduled three synthetic contract templates × two repetitions
× three arms × two feedback policies = **36 runs**. All completed, including
12 fixed-checklist runs that made no model call. Reference answers were excluded
from model inputs. All provider attempts used the same profile and shared budget.

Inspection found an implementation defect in the supplied context:
`known_duplicate_hours: [8, 12, 16]` could naturally mean that each individual
hour was a duplicate. The authoritative rule instead compares the entire
normalized diagnostic, including the complete hour array. Models consequently
rejected valid subsets. This is a flawed test input, so its apparent accuracy
and Critic-benefit estimates cannot support a model-quality conclusion.

An operator correction event was appended to all 36 runs. Original answers,
usage, references and task exposure remain available; the current comparison
has `integrity: INVALID` and null authoritative accuracy summaries in
[process_summary.json](process_summary.json).

Context revision `exact_diagnostic_identity/2` supplies a complete known
diagnostic and an explicit equality rule. The remaining three campaign runs
were preregistered as corrective smoke checks on **already exposed tasks**:

| Corrective check | Expected | Recorded |
| --- | --- | --- |
| Single agent, supported hour subset | `REVIEW` | `REVIEW` |
| Research + Critic, supported hour subset | `REVIEW` | `REVIEW` |
| Single agent, declared missing news source | `BLOCKED_DATA_REQUIREMENT` | `BLOCKED_DATA_REQUIREMENT` |

[process_correction.json](process_correction.json) contains the three records.
These checks verify the correction. They are not a replacement full comparison,
a fresh holdout, proof of Critic benefit or evidence of open-ended discovery
quality. The original suite was not rerun beyond the frozen campaign allowance.

## Resources and verification

The campaign stopped at **40 registered runs**: one discovery run, 36 initial
process runs and three corrective checks. It contains 76 provider invocations
with 92,006 reported input tokens and 9,403 output tokens. Conservative retained
reservations total **USD 24.187702 of USD 50**. Applying the profile's highest
input/cache-write price and output price to reported tokens gives USD 1.620225;
this is a token-price estimate, not a reconciled invoice. Cached-input discounts
may reduce the actual amount. No budget was refunded or reset for the invalid
suite.

Verification included 55 passing unit, API-contract and disposable PostgreSQL
integration tests; migration apply/downgrade/reapply on the disposable database;
real migration and legacy import; real provider capability checks; role denials;
concurrent token/money reservations; timeout retention; atomic draft/tool audit;
operator design freeze and candidate lock; evidence/process invalidation; and
recorded replay. The capture, ingress and PostgreSQL containers remained healthy
with their existing container identities.

The real blocked draft was not admitted or evaluated. The operator admission
path was exercised against test fixtures only. No source CSV was scanned again,
no trading instruction was issued and no new economic evidence was measured.
Independent validation, credible costs, meaningful research novelty, general
calibration and a valid broader agent comparison remain open work. The next
process study needs a separately frozen allowance and must retain this suite's
exposure and defect history.
