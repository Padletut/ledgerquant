# Human review: six proposed process assessments

**Prepared:** 10 October 2026. **State at export:** all six assessments are `PROPOSED`; none has been approved by this export.

**Review update, 10 October 2026:** the user has reviewed all six assessments.
See the [recorded human decisions and reviewed pages](reviewed/README.md) for
their `REVIEWED` supersessions, remaining uncertainties and one released method
lesson. The six original pages below retain their original proposed-state
snapshots; their source states are no longer current.

## What you are deciding

You are checking whether Claude's claims about a recorded research action are
supported by what the agent wrote, the information it received and the rules
then in force. You can agree, disagree, narrow a claim or leave it unresolved.
You are not approving a trading strategy or judging an agent by later profit.

Each page below contains the proposed finding, **the exact cited source text**,
the original proposal or critique, supplied catalog rules and declared limitations.
The linked `.source.json` contains the complete recorded assessment and its
packet. IDs and hashes are in the audit section; they identify the record and
detect changes, but are not the substance of the review.

## Start with a pair of pages

Read Research before Critic for each run. The Critic assessment sometimes depends
on whether you accept the alleged Research defect.

| Case and page | What Claude proposes; what you should check |
| --- | --- |
| **Astra — [Research](e7f85e02-research.md)** | F1: the proposal put broker costs in a binding required-data field while saying they were needed only for a future economic test. Does that constitute a requirement-scope error under v1? F2–F4: Claude says evidence attribution, contrary evidence and the predictive falsifier do **not** establish defects; check these claims too. |
| **Astra — [Critic](e7f85e02-critic.md)** | F1: did Critic miss that visible field/prose contradiction? F2: did it correctly distinguish aggregate results from the unmeasured 12 UTC subset? |
| **Mini v2 — [Research](23632117-research.md)** | F1: did “the same diagnostic” incorrectly present an aggregate result as evidence for the 12 UTC subset? F2: did the falsifier mix a predictive test with an administrative admission rule? F3 keeps lineage attribution unresolved because v2 lacked a linked-revision route. F4 says cost scope was correctly deferred. |
| **Mini v2 — [Critic](23632117-critic.md)** | F1–F2: did Critic miss the two alleged defects? F3: was its cost-scope assessment correct? F4: should lineage remain an unresolved service issue instead of a confirmed Critic error? |
| **Linked revision — [Research](d6149cdb-research.md)** | F1–F4: Claude finds no supported defects in attribution, lineage, cost scope or the falsifier. Check each conclusion and the authorship limit: the service copied the substantive proposal from its parent. Correct inherited text does not by itself demonstrate a new Research capability. |
| **Linked revision — [Critic](d6149cdb-critic.md)** | F1: was the citation rejection caused by the service's namespace check, rather than invalid citations from Critic? F2–F3: did Critic correctly assess cost scope and the predictive falsifier? Check the linked Research comparisons separately. |

These are **21 proposed findings**, not 21 confirmed mistakes. The six pages
contain both proposed defects and proposed findings that a defect is absent.

### The first finding in plain language

The Astra proposal put `broker_costs` in its required-data list. The reason inside
that very item says:

> This blocks economic interpretation, not the present no-trade price diagnostic

The review question is whether putting a future prerequisite into a binding
current requirement contradicted the proposal's stated scope under the then-active
contract. The question can be answered without checking whether its market
prediction later won or lost. The [first page](e7f85e02-research.md#f1--current-versus-future-data-requirements)
shows the full field, the mechanism and Claude's explanation together.

## Decision vocabulary

| Your finding label | Meaning |
| --- | --- |
| `SUPPORTED` | The alleged defect is supported by the cited evidence and applicable rule. Check attribution and scope as well. |
| `NOT_SUPPORTED` | The evidence does not support that allegation. This does not certify the agent or strategy as generally good. |
| `UNRESOLVED` | The evidence or applicable rule is insufficient or ambiguous; retain the uncertainty and say what is missing. |

`REVIEWED` is a **record-level state**: a person has reviewed the findings. A
reviewed record can contain all three finding labels. You need not agree with
Claude, and you need not approve all six records together. A method lesson needs
its own cited assessments to be reviewed and current; unrelated pending records
do not block that lesson. The lesson's wording and applicability still need their
own review before release.

For each finding, check:

1. Does the quoted text actually support the claim, including the rule in force?
2. Is the named component responsible: Research, Critic, service or an unresolved source?
3. Are severity and applicability justified, or is the claim too broad?
4. Does the reasoning use later payoff, a corrected checker result or a missing capability as an unfair agent-quality label?

If a claim needs information absent from the packet, request that information or
leave it unresolved. A hash match establishes source identity, not correctness.

## How to provide your review

You can respond in ordinary language using the page name and finding number:
for example, identify “Astra Research, F1”, state your chosen label and explain
any correction. Explicitly say when you consider that record reviewed. An
assistant can prepare and submit the corresponding command from your decisions;
it must not invent your verdict or identify itself as a human reviewer.

The author of the current assessments declared **outcome exposure**. Your own
replacement must also record your actual exposure; reading earlier results in
this conversation cannot be undone by opening a sealed packet. These remain
retrospective reviews, not assessments made before the original experiment.

The recording steps, after your decisions are concrete, are:

1. Refresh the assessment with `process-review --assessment-id ID`. Confirm that
   it has not been superseded and the packet still matches. The export date and
   source state here are snapshots, not a live status display.
2. Prepare a **new** `ProcessAssessment` command from the original config file.
   Preserve run/role and source hashes; set `supersedes` to the recorded assessment
   ID. Record the new assessor, actual outcome exposure, reviewer, chosen findings,
   limitations and reason. Set `review_state` to `REVIEWED` only following the
   explicit human review. Do not edit the original command or its registered record.
3. Submit Research first with `assess-process --decision FILE`. Use its returned
   assessment ID in any replacement Critic `critic_delta` that refers to that
   newly reviewed Research finding; reconsider those comparisons if your finding changed.
4. Submit the reviewed Critic replacement. Deriving and releasing a method lesson
   is a separate operation. A held-out feedback comparison still requires its
   preregistered task families, references, budget and stopping rule.

The existing schema records reviewer identity as an operator-supplied string; it
does not authenticate a human. Explicit review decisions and operator audit are
therefore necessary. This reading interface grants no approval or new research budget.

## Sources and regeneration

The original command files and bookkeeping index are in
[process_assessments](../../../../configs/research/process_assessments/INDEX.json).
The six `.source.json` files here were read from PostgreSQL in a `READ ONLY`
transaction. Their assessment and packet hashes matched the recorded IDs and
the current sealed packets at export. The Markdown pages are generated from those
exact sources by `research.process_review`; PostgreSQL remains authoritative.

The new read-only CLI operation supports:

```text
python -m ledgerquant.research.agent_cli process-review --assessment-id ID
python -m ledgerquant.research.agent_cli process-review --assessment-id ID --format json
```

Use the database environment described in the [operations guide](../../../operations/RESEARCH.md#reading-and-reviewing-the-six-assessments).
The operation neither calls a model nor records a decision. The JSON form retains
the complete sources; the Markdown form expands the references into readable text.
