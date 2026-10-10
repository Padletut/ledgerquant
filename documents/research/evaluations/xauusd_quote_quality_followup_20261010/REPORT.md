# XAUUSD quote-quality Research/Critic follow-up

**Status:** exploratory, unmeasured. No candidate was frozen, no evaluator ran,
and no 2021 quote outcome was opened.

On 10 October 2026, one bounded `gpt-5.4-mini` Research → Critic run revisited the
[XAUUSD development audit](../../../data/measurements/xauusd-quote-quality-audit-v1.json)
and [recent-spread baseline](../../../data/measurements/xauusd-quote-quality-baseline-v1.json).
The source task identified these files by SHA-256 and supplied only their
2020 development summary. The runtime also supplied the recorded parent idea
and its Critic review. No account number, raw tick file or 2021 outcome entered
the task.

The first registered attempt (`88be6cb0-0f71-4a75-b9f0-63c427997b6e`)
stopped at the capability probe with a `ConnectError`, before any model output.
Its invocation and USD 0.021996 reservation remain in the local registry.
After explicit operator approval for this XAUUSD payload, one technical retry
(`1392beab-84c4-4ef3-870b-b9d65f8c09d9`) completed. It recorded a Research
draft (`fea381475e946ee36f0e0767051979208f65f0292188f543fc55339fdf2e4abd`)
and Critic review (`cf105829aee065f79811c3b150ccced6ef7724240fd73941253718ce580f770c`).
The provider returned `gpt-5.4-mini-2026-03-17`. The completed run recorded
6,029 input and 3,098 output tokens and reserved USD 0.086214. Reservations
are not billed-cost records. Full model inputs, outputs, tool calls and exact
lineage are retained in the ignored local research registry and
`data/research_control/operator/xauusd_quote_followup_20261010/`.

Research proposed checking whether prior-30-minute spread IQR adds information
beyond the preceding-15-minute spread p95 for the next-15-minute p95. It
acknowledged the weak baseline comparison: IQR was ahead on only three of six
2020 development days, with mean daily rank-correlation difference −0.065.
Critic correctly highlighted timing, quote fidelity, overlap and the absence
of a fixed comparison rule.

## Operator assessment

- The recorded `proposed_decision` asks whether to *keep researching* the idea.
  It does not define the broker-facing abstention decision from the parent
  hypothesis. The recorded `proposed_payoff` is quote quality, not an economic
  payoff from abstaining. Critic did not identify this change of decision scope.
- A split of the six 2020 dates can be a development sensitivity check, but all
  six dates' outcome summaries were already inspected. Calling a new split an
  independent or untouched holdout would overstate the evidence. Critic did
  not make that exposure distinction clearly enough.
- The proposed feature and baseline are both knowable from past quotes in an
  event-time backfill. Actual historical `available_at`, feed latency and
  broker-actionable quote fidelity remain unknown.

**Disposition:** retain the linked draft and review as an exploratory attempt.
Do not admit or freeze it as a new payoff contract, and do not use the 2021
outcomes to rescue it. A later 2020-only conditional comparison could clarify
whether IQR adds information to recent spread, but it must be labeled
development analysis and must state the exact comparison before computation.
It would still not establish an abstention payoff or a trading edge.
