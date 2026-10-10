# Human-reviewed process assessments

**Reviewed:** 10 October 2026, by the human user via the project conversation.
**Recorded:** 10 October 2026, 00:26 UTC. Codex transcribed the decisions.
**State at export:** six `REVIEWED`, current assessments; one released `METHOD_LESSON`.
**Reviewer and assessor outcome exposure:** `EXPOSED`.

These records assess the recorded proposal or critique against its information
and constraints. `SUPPORTED` means the alleged process defect has support;
`NOT_SUPPORTED` means it does not; `UNRESOLVED` preserves uncertainty. `REVIEWED`
records the human review, including rejected allegations and unresolved findings.
All six original assessments remain stored and are superseded by the new records.

## Decisions

| Reviewed assessment | F1 | F2 | F3 | F4 |
| --- | --- | --- | --- | --- |
| [Astra Research — e7f85e02](e7f85e02-research.md) | SUPPORTED | NOT_SUPPORTED | NOT_SUPPORTED | NOT_SUPPORTED |
| [Astra Critic — e7f85e02](e7f85e02-critic.md) | SUPPORTED | NOT_SUPPORTED | No finding | No finding |
| [Mini v2 Research — 23632117](23632117-research.md) | SUPPORTED | SUPPORTED | UNRESOLVED | NOT_SUPPORTED |
| [Mini v2 Critic — 23632117](23632117-critic.md) | SUPPORTED | SUPPORTED | NOT_SUPPORTED | UNRESOLVED |
| [V3 Research — d6149cdb](d6149cdb-research.md) | NOT_SUPPORTED | NOT_SUPPORTED | NOT_SUPPORTED | NOT_SUPPORTED |
| [V3 Critic — d6149cdb](d6149cdb-critic.md) | NOT_SUPPORTED | NOT_SUPPORTED | NOT_SUPPORTED | No finding |

There are **6 supported, 13 not supported and 2 unresolved findings**. Research
and Critic assessments share process cases; these counts are neither independent
observations nor estimates of agent error rates. Finding numbers are local to
each assessment; the linked pages show the allegation and exact cited text.

- **Astra:** Research's binding requirement declaration was inconsistent with
  its current scope, and Critic missed that defect. The evidence scope, contrary
  evidence and conditional predictive falsifier do not support the other Research
  allegations. Critic F2 confirms the absence of an attribution defect. The
  detailed two-finding Critic section in the human response determines its mapping;
  no Critic F3/F4 were added.
- **Mini v2:** Research misattributed evidence and mixed predictive falsification
  with administrative eligibility. Critic missed both and correctly handled the
  requirement scope. The duplicate-versus-revision questions remain unresolved,
  attributed to `contract_service`, with material severity.
- **V3:** The reviewed allegations are not supported. Much substantive proposal
  content was inherited or service-constructed. Absence of these defects does
  **not establish newly acquired independent Research capability**. Critic
  recognized the predictive/administrative distinction in the clean inherited
  falsifier; comparing this with the missed Mini v2 defect does not isolate learning
  or a feedback effect.

All Critic deltas now reference the reviewed Research assessment for the same run.
Original finding codes, statuses, components and severities were retained because
the human decisions confirmed them; the replacement records add explicit review
provenance and the limitations above.

## Released method lesson

The human reviewer supplied this claim, recorded verbatim:

> When reviewing a typed proposal, Critic must compare binding structured requirements against the proposal's stated current scope. Agreement between the prose and Critic's own interpretation is insufficient if the binding field expresses something different.

The [feedback record](requirement_scope_method_lesson.source.json) cites the new
Astra Research and Critic assessments and groups them under their single process
lineage. Availability starts at **2026-10-10T00:26:11.766907+00:00**, when the
registry released it. It cannot enter an earlier historical context.

The [selection export](feedback_selection.json) verifies eligibility under
`reviewed_method_feedback/1`; no agent was invoked with this feedback. Its
applicability and counterexamples retain the distinction between current and
future requirements, checker defects and agent errors, and process quality and
economic value. Feedback benefit remains unmeasured.

## Engineering lesson: reference resolution

The human reviewer identified a separate engineering lesson:

> Reference checker must resolve authorized frozen fact hashes as well as evidence-record IDs.

The [reviewed V3 Critic F1](d6149cdb-critic.md#f1--evidence-attributed-to-the-wrong-scope) cites the
recorded `CITATION_NAMESPACE_DEFECT` correction. The existing
`scoped_registry_references/1` policy implements that correction. Valid citations
in this case do not support a negative Critic lesson saying it cited evidence
incorrectly. This engineering note is retained here with its source; no new
feedback type or agent-facing citation-error lesson was registered.

## Audit and verification

The [command index](../../../../../configs/research/process_assessments/reviewed_20261010/INDEX.json)
and [registration receipts](../../../../../configs/research/process_assessments/reviewed_20261010/RECEIPTS.json)
map originals, replacements and the released lesson. Each reviewed page includes
the immutable source export. The [original review guide](../README.md) and its
six original pages remain snapshots of the proposed assessments.

Verified against PostgreSQL after registration:

- All six new assessments are current and reviewed; all six originals are
  unchanged and superseded.
- Stored and current packet hashes match the reviewed sources for every record.
- Every Critic delta links to a current reviewed Research assessment.
- The single released lesson has exact reviewed source hashes and is selected by
  the read-only feedback query.
- Counts of research runs, drafts, critiques, tool calls, evidence and commitments
  are unchanged across registration.

This review did not run a new agent invocation, market evaluation or held-out
comparison. It does not change historical admission, outcome exposure, economic
evidence or the unresolved lineage findings. The held-out study still needs its
own frozen contract, withheld families and budget.
