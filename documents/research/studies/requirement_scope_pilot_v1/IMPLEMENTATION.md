# Requirement-scope pilot: archived implementation

**Date:** 10 October 2026

**Architecture:** 2.18 · **Implementation plan:** 1.11

**State:** Retired from active code. Preparation stopped before inference as
`INSUFFICIENT_FAMILY_DIVERSITY`; **DO_NOT_START** remains in force.

## Reason and current scope

The one-off pilot introduced seven modules, six offline commands and 14 tests
before demonstrating a useful feedback effect. Its fixed 24-case/eight-family
allocation and extensive reference workflow were too costly to maintain for the
current solo project. The package and its test module have been removed from
`src/` and `tests/`: 669 application lines and 246 test lines.

Routine research continues through the existing Research/Critic runtime,
registry and evaluator. No replacement framework, new schema, provider run or
automatic authority was introduced. Human review still governs certified
process findings and method release until an evaluated replacement is activated.

## Preserved history

The [implementation archive](implementation.tar.gz) contains the exact 54 files
bound by the original [implementation freeze](../../../../configs/research/studies/requirement_scope_pilot_v1/implementation.freeze.json),
that manifest, dependency files, and the original implementation/readiness
documents. All 60 members use repository-relative paths. The archive checksum
is recorded in the derived [status record](../../../../configs/research/studies/requirement_scope_pilot_v1/readiness.json).
This is a historical source snapshot, outside application imports and normal test
discovery. Inspect it with `tar -tzf`; restore only into a separate checkout of the
manifest's base commit when investigating the old implementation.

The original [protocol](PROTOCOL.md), design, cases, review receipts and
[readable case pages](review/README.md) remain in place. The [review status](REVIEW_STATUS.md)
preserves all 24 supplied decisions, accepted rationale criteria, case 15
clarification and declared `AI_ASSISTANT` reviewer provenance. Operator-only
author notes and review records remain under the existing ignored
`data/research_control/operator/requirement_scope_pilot_v1/` directory and still
need operator backups. The archive contains no credentials or private reviews.

Historical blank forms, commands and unfinished prerequisites are retained for
traceability. They are not active work instructions, and no further review is
requested to complete this retired pilot.

## Verification and limits

- Before retirement: 90 unit tests passed, including the 14 pilot tests.
- Every archived source byte matches its original frozen SHA-256; original
  design/candidate freezes and review artifacts are preserved.
- The stopped pilot made zero provider calls and allocated no campaign funds.
  Its offline compiler projected USD 1.850928 for 96 proposed requests under the
  historical tariff; this was neither spend nor an execution authorization.
- Runtime dispatch, isolation for this pilot, a complete human reference set and
  model/feedback performance were never established. Archiving adds no evidence
  to those claims. The separate current unit suite checks the retained runtime.
