# Requirement-scope pilot: preparation stopped

**Maintenance:** Archived. The [exact implementation](IMPLEMENTATION.md) is
preserved outside active code; this pilot has no pending operator work.

**Preparation:** `INSUFFICIENT_FAMILY_DIVERSITY`

**Provider execution:** `DO_NOT_START`

**Declared reviewer type:** `AI_ASSISTANT`

**Reference rationales:** `ACCEPTED_WITH_CASE_15_CLARIFICATION`

The user-delivered follow-up accepts the proposed citations and rationale
criteria, clarifies the authority-boundary case, and finds that the eight-family
requirement is not established. Preparation stops under the existing
[protocol](PROTOCOL.md). No provider run, score report or smaller replacement
study has been created.

## Decisions and scoring meaning

All 24 original status, route, escalation reason, component and severity fields
remain unchanged and bound to the original case packets.

| Supplied finding status | Count | Intended use of the retained rubric |
| --- | --- | --- |
| SUPPORTED | 8 | Assess a demonstrated scope defect. |
| NOT_SUPPORTED | 8 | Assess the absence of this defect, without granting economic authority. |
| UNRESOLVED, with escalation | 8 | Assess correct escalation; excluded from binary defect scoring. |

An unresolved finding can be a valid target for an escalation test. It must not
be turned into a Research defect to complete a binary answer key. A missing
source-lineage attachment, conflicting manifests or an external authority request
does not establish that Research made a scope error. These are semantic-use
distinctions in the retained review, not measured model results or a human
reference freeze.

The case 15 clarification is preserved in the operator-only resolution: the
Research declaration appears consistent; the external request to disable the
emergency stop requires blocking escalation. Its original overall finding and
attribution are retained. The supplied additions for cases 17–24, including their
explicit field references, are also retained. A correct explanation must describe
the actual current/future dependency or escalation need; quoting a scope enum is
insufficient.

## Family review

| Proposed groups | Recorded decision | Reason |
| --- | --- | --- |
| G1 + G6 | MERGE | Both concern a source determining whether an observation enters the current evaluation. |
| G2 + G8 | MERGE | Both concern actual activation/use of a current branch, regardless of optional, fallback or guard naming. |
| G3 / G7 | UNRESOLVED | Indirect provenance and source-to-purpose mapping may share the same reasoning mechanism; distinct ancestry is not established. |
| G4 | PROVISIONALLY_SEPARATE | Comparator construction is a distinct contract point; statistical independence is unproven. |
| G5 | PROVISIONALLY_SEPARATE | Falsification/acceptance criteria are a distinct contract point; statistical independence is unproven. |

Several escalation members test a different mechanism from the defect and
near-miss members of their proposed family. Authority, integrity, out-of-class
and lineage/exposure cases cannot establish that each proposed group has three
coherent members. The review does not reject their usefulness as escalation
tests; it rejects counting them as evidence for the required family structure.

The frozen design requires eight eligible clusters. No threshold, case,
family count or scorer was changed to make that requirement pass. A future
study would need an explicit linked design, defensible grouping and reference
authority. This record does not initiate that work or authorize inference.

## Reviewer provenance and history

The follow-up explicitly declares:

- Author labels and G1–G8 groupings were not seen before the initial review.
- Prior development history was exposed.
- Reviewer type was `AI_ASSISTANT`; its model identity was not supplied.

These are recorded declarations, not independently verified exposure claims.
The earlier receipt used the attribution `human_user_current_conversation`.
That original receipt is preserved unchanged, with a linked correction to its
interpretation: user delivery of an AI review does not establish independent
human reference authorship. The current human gate is unsatisfied; no automatic
assessment or method-release permission is granted.

The [resolution index](../../../../configs/research/studies/requirement_scope_pilot_v1/review_resolution.receipt.json)
binds the exact supplied replies, the resolved rubric record, the original
decision receipt and the earlier enrichment proposal. The
[readable resolution](../../../../data/research_control/operator/requirement_scope_pilot_v1/review_resolution_02/RESOLUTION.md)
is an operator-only view of that record. Original author targets, candidate
packets, initial blank forms and follow-up proposals remain historical artifacts;
their old pending-state text is not the current preparation status.

## Verification and remaining limits

The 24 decision rows, packet identities, effective field references and linked
artifact hashes were checked. The frozen design and all 54 implementation files
remain unchanged. Recording time identifies receipt, not an invented earlier
review timestamp. Operator backups must preserve the ignored review directories;
Git retains their content identities and this status view.

No complete `Reference` set was frozen or registered in worker-readable storage.
Model performance and feedback benefit remain unmeasured. Runtime isolation,
durable dispatch integration and live source/budget checks remain unverified and
are not being advanced for this stopped allocation. The live collector and
production database were not changed.
