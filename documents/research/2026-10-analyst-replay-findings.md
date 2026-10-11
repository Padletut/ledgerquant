# Analyst replay findings, October 2026

Replay of single LLM analysts (GPT-5.4 mini, Claude Opus 4.6) over seven post-cutoff
weeks, 11 October 2026. Branch `research/analyst-v4`. All runs are retrospective
simulations with fresh inference over backfilled data; none used recorded outputs.

## 1. Verdict

The question tested was: given the point-in-time context LedgerQuant can build
today (quotes and bars, GDELT headlines, FRED macro vintages, release dates,
market times, an estimated swap), can a single LLM analyst pick direction and
levels at hourly decision times with an edge after costs?

**No.** Both models behave as 23-hour momentum followers with a narrative: 81-85 %
of their entries go with the prior day's move. With momentum they earn roughly
what the free rule earns; the few times they go against it they lose. Neither
beats always-long, always-short or 23-hour momentum per entry over the same
decision times. The profit that appears (GPT in October 2025, Claude in the same
week) is the gold trend of that week, not skill. Costs are not the cause: spread,
commission and swap are about 0.04 R per trade at the geometries used.

The cause is structural, not a small sample: the context contains no information
the price does not already have. The news view agrees with the chart view in 95 %
of entries, the headlines describe moves that have already happened, macro
vintages are days or weeks old, sentiment is unavailable for the whole period and
the calendar has dates only. More weeks of the same recipe would narrow the
confidence interval around the same answer.

The infrastructure built for this test (tick archive, point-in-time context,
cost model, limit check, free-rule baselines, two provider adapters) is sound and
independent of the result.

## 2. What was run

| Item | Value |
| --- | --- |
| Instruments | EURUSD, GBPUSD, XAUUSD (IC Markets EU terms) |
| Decision times | every full hour 07-20 UTC on trading days, 210 per week |
| Weeks | 2025-09-08, 2025-10-13, 2025-11-10, 2025-12-08, 2026-01-12, 2026-02-09, 2026-03-09 |
| Labels | all `DEVELOPMENT`; both models' published training cutoff is August 2025; the holdout 2026-09-01 to 2026-10-08 is untouched |
| Contracts | `analyst/3` (fixed maximum holding time 15-1440 min) and `analyst/4` (style and expected horizon, no holding limit, costs in the instructions, symmetric LONG/SHORT guidance, user weekend-close limit) |
| Models | `gpt-5.4-mini` (reasoning effort medium, strict schema, tool call required) for analyst/3 and analyst/4, seven weeks each; `claude-opus-4-6` (adaptive thinking, effort medium, tool call under `tool_choice: auto`) for analyst/4, three weeks: 2025-10-13, 2025-12-08, 2026-03-09 |
| Positions | one shadow position per symbol at a time, market entry at ask/bid, tick-by-tick stop and target, agent review every hour (`HOLD`/`CLOSE`/`ADJUST`), close at the weekly close (Friday 17:00 New York) under analyst/4 |
| Costs | spread via bid/ask; commission 30 USD per million USD per side; swap from the policy-rate differential visible at the time minus a markup calibrated from the broker's terms read on 2026-10-11 (`configs/broker_terms/icmarkets-eu-real.json`) |
| Context | `replay_context`: latest quote, M5/H1/D1 bars, GDELT headlines of the last 6 hours (backfill visible 15 min after batch), central-bank releases, FRED/ALFRED vintages (visible the day after `realtime_start`), release dates, market times, estimated swap; sentiment `UNAVAILABLE` throughout |
| Spend | OpenAI 42.66 USD over 2,972 calls; Anthropic 66.48 USD over 646 calls (both include smoke tests and two aborted starts) |

Run directories (`data/replay_runs/`): analyst/3 `20261011T012052Z`, `013802Z`,
`013804Z`, `013806Z`, `015553Z`, `024808Z`, `033956Z`; analyst/4 GPT
`20261011T035609Z_…_20250908` through `042050Z_…_20260309`; Claude
`20261011T051432Z_…_20251013`, `054856Z_…_20251208`, `062548Z_…_20260309`.
Smoke runs (`011649Z`, `011817Z`, `012015Z`, `025226Z`, `050933Z`) and the two
aborted starts in `_aborted/` are excluded from every statistic below. Each run
directory holds `run.json` (variant, hashes, plan), `decisions.jsonl` (full
context, request hash, raw provider response, validation status, cost),
`trades.jsonl` (entry, exit, adjustments, static and mirrored comparisons) and
`REPORT.md`.

## 3. Results

### 3.1 Totals per variant

R = price move divided by the initial stop distance. Net = after spread,
commission and estimated swap. analyst/3 runs recorded gross R only; the net
figure applies the same cost model after the fact.

| | GPT analyst/3 | GPT analyst/4 | Claude analyst/4 |
| --- | ---: | ---: | ---: |
| Weeks | 7 | 7 | 3 |
| Model calls | 1,470 | 1,470 | 630 |
| Valid answers | 1,467 | 1,465 | 629 |
| Trades | 215 | 120 | 23 |
| LONG / SHORT | 160 / 55 | 78 / 42 | 8 / 15 |
| Gross R | −7.0 | +0.5 | +7.2 |
| Net R | −13.3 | −3.5 | +6.8 |
| Net R per trade | −0.06 | −0.03 | +0.29 |
| 95 % interval, per trade | −0.14 … +0.07 | −0.24 … +0.18 | −0.15 … +0.74 |
| Win rate | 47 % | 37 % | 52 % |
| Profit factor | 0.90 | 0.94 | 1.82 |
| Entries with 23 h momentum | 182 (85 %) | 102 (85 %) | 19 (83 %) |
| Exits | TARGET 15, STOP 83, MAX_HOLDING_TIME 100, AGENT_CLOSE 17 | TARGET 35, STOP 43, AGENT_CLOSE 28, WEEKEND_CLOSE 14 | TARGET 10, STOP 5, AGENT_CLOSE 6, WEEKEND_CLOSE 2 |
| Median holding | 4.0 h | 7.7 h | 6.5-16.6 h by week |
| Cost | 20.75 USD | 21.47 USD | 64.81 USD |
| Latency, median | 5-7 s | 5-6 s | 27-31 s |

### 3.2 Week by week, net R

| Week | GPT v3 trades / R | GPT v4 trades / R | Claude trades / R | Always long | Always short | Momentum 23 h |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2025-09-08 | 31 / −7.0* | 12 / −1.8 | | −0.23 | −0.13 | −0.36 |
| 2025-10-13 | 42 / −0.3* | 22 / +15.9 | 9 / +6.3 | +0.60 | −0.46 | +0.38 |
| 2025-11-10 | 38 / −1.3* | 24 / −3.0 | | +0.12 | −0.27 | −0.17 |
| 2025-12-08 | 25 / +9.7* | 17 / −5.5 | 3 / +0.3 | +0.38 | −0.49 | −0.10 |
| 2026-01-12 | 30 / −4.2* | 18 / −2.4 | | −0.72 | +0.76 | +0.16 |
| 2026-02-09 | 21 / −3.0* | 10 / −3.9 | | −0.29 | −0.05 | −0.38 |
| 2026-03-09 | 28 / −1.1* | 17 / −2.8 | 11 / +0.2 | −0.53 | +0.61 | +0.35 |

\* gross. Rule columns are net R per entry from the analyst/4 GPT report of that
week; rules enter at every ready decision time with the agent's median geometry
(or the declared default when the agent made fewer than five trades on a symbol),
are held to stop, target or the weekly close and are netted of the same costs.

### 3.3 Agent against the free rules, per entry

Means of the weekly means, net R per entry.

| | Always long | Always short | Momentum 23 h | Agent |
| --- | ---: | ---: | ---: | ---: |
| GPT v3, 7 weeks | −0.08 | −0.01 | −0.01 | −0.06 |
| GPT v4, 7 weeks | −0.09 | −0.00 | −0.02 | −0.03 |
| Claude, 3 weeks | +0.15 | −0.17 | +0.16 | +0.29 |

Over seven weeks every rule and both GPT variants sit at zero or below. Claude's
three weeks were not a random sample: they were chosen as a trend week, a
Fed-meeting week and a falling week, and the momentum rule itself averaged +0.16
per entry in them against −0.02 over all seven. Claude's +0.29 is within one
standard error of that rule.

## 4. Why

### 4.1 The agents follow 23-hour momentum

Splitting every entry by the direction of the previous 23 hourly closes, held to
stop, target or the weekly close (net R):

| | With momentum | Against momentum | Mirror of the against-momentum entries |
| --- | ---: | ---: | ---: |
| GPT v3 | 182 trades, +0.11 per trade | 33 trades, −0.16 | +0.22 |
| GPT v4 | 102 trades, +0.08 | 18 trades, −0.33 | +0.25 |
| Claude | 17 trades, +0.37 | 4 trades, −0.04 | |

With momentum the agents earn what the rule earns. The entries where they used
independent judgement, against the prior move, lost, and the opposite direction
would have won. The model's own contribution to direction is zero or slightly
negative on this evidence.

### 4.2 The news view is not an independent source

In 318 of 335 GPT entries (95 %) the news view and the chart view gave the same
stance; no entry was driven by the news view alone. The newest cited headline was
typically half an hour old and reported a move already visible in the bars. FRED
vintages are released days to weeks after the period they describe. The release
calendar holds dates without times or consensus figures. Sentiment was
`UNAVAILABLE` at every decision time (capture started 8 October 2026; there is no
history, see `documents/data/DATA_AVAILABILITY.md`). The agents therefore read
the same thing from the news that they read from the chart.

### 4.3 FX direction is a coin flip; stops and costs are not the problem

- After an FX entry the mid had moved in the trade's direction at 1, 4, 8 and 24
  hours in 39-52 % of cases (gold: 55-64 %).
- Stops sat about 2.1-2.4 mean hourly ranges and about half a daily range from
  the entry. Before a stop the trade had reached a median of 0.3-0.4 R in its
  favour; 20-33 % of stopped FX trades reached the target later in the week,
  consistent with random paths. Wider stops would not have saved them.
- Costs per trade: commission ≈ 0.02 R, swap ≈ 0.013 R, spread ≈ 0.003 R.

### 4.4 Gold profit is the gold trend

Always-long gold at every decision hour with the declared geometry returned
+59.9 R over the seven weeks (+0.12 per entry, 490 entries); always-short −38.4.
GPT's gold longs earned +0.47 (v3) and +0.61 (v4) per trade, better than the
rule per entry, but with 76 and 30 trades that is a hypothesis, not evidence.
Without gold longs, v3 held under common rules was −30.5 R net and v4 −20.1 R.
On EURUSD and GBPUSD both GPT variants lost 0.1-0.4 R per trade, worse than the
mean of always-long and always-short (−0.02 to −0.06).

### 4.5 Position management

analyst/3 adjusted stops 139 times and was cut by its own holding limit 100
times; its entries held under the analyst/4 rules would have made +14.0 R gross
against the −7.0 realised, so management cost about 21 R. analyst/4 adjusted
zero times, closed 28 times and held 935 times; its managed result (+0.5 gross)
is within 2 R of the static exit (+2.7 gross). In analyst/4 INTRADAY entries made
+12.0 R gross over 98 trades and SWING −11.4 R over 22. Claude's management added
+0.4 R in October and was neutral otherwise.

### 4.6 The weekend limit and the hindsight number

The deterministic check that rejects an entry whose expected horizon exceeds the
hours to the weekly close (`replay/risk.py`) fired zero times in 2,100 analyst/4
decisions: both models always fitted the horizon to the time left and kept
taking short Friday trades. The limit cost performance only through forced
closes (14 GPT, 2 Claude trades).

The "+29.9 R" discussed during the work was analyst/3's entries held open-ended,
gross, over five weeks, in hindsight. Like for like (weekly close, net) the same
entries made +5.4 R, analyst/4's entries −1.9 R; the difference is 76 versus 30
gold longs.

### 4.7 Claude

Claude Opus 4.6 traded far less (23 trades in three weeks against 56 for GPT in
the same weeks), chose SWING in 19 of 23 trades, mostly with 48-hour horizons, cited no unknown IDs, and
waited for scheduled events: in the Fed week of 2025-12-08 it answered WAIT at
118 of 210 decision times, 109 of them for an event, in a chain from the FOMC
through claims data, the Bank of England and UK GDP. Acting on its own stated
direction at those WAIT times would have lost 28.3 R in December (its caution
paid) and forgone 16.5 R at NO_SIGNAL times in October (its caution cost). It was
right about direction in March (11 shorts in a falling market) but five Monday
entries were stopped out before the move came, and the week ended at +0.2 R while
the momentum rule made +0.34 per entry.

Operationally: 0.10 USD and 27-31 s per decision; one invalid answer in 630
(views sent as a JSON string); 23 answers with a reason over the 500-character
limit, which the pipeline now truncates and records (`truncated_text_fields`)
because Opus 4.6 has no strict tool schemas. In the smoke test and the first,
aborted start it was one answer in seven; without the fix those decisions would
have been rejected and Claude handicapped against GPT.

## 5. Statistical reading

- With standard deviations of 0.8-1.2 R per trade, 120-215 trades give standard
  errors of 0.05-0.10 R per trade. An edge of ±0.05 R per trade, which is what
  the free rules show in either direction, cannot be distinguished from zero at
  this size; neither can an edge be excluded by the intervals alone. The
  conclusion rests on the mechanism in Section 4, which does not depend on the
  sample size.
- Common thresholds for continuing a strategy (at least 100 trades, profit
  factor above 1.5, out-of-sample Sharpe above 1) are not met by either GPT
  variant (profit factor 0.90 and 0.94). Claude's 1.82 comes from 23 trades,
  93 % of its total from one week.
- Variants tried: analyst/1 and analyst/2 (schema fixes, smoke only), analyst/3,
  analyst/4 on GPT, analyst/4 on Claude. analyst/4's design changes (no holding
  limit, costs and symmetric guidance in the instructions, weekend limit) were
  made after reading analyst/3's results, so analyst/4 is not blind to these
  weeks; no numeric parameter was fitted to them, and the free-rule geometry and
  the WAIT thresholds are declared defaults.
- Each week was run once per variant; the spread from model non-determinism was
  not measured by repeated runs.
- The holdout has not been touched.

## 6. What works and what was fixed

Working and verified by tests (85 unit tests): the tick archive and
point-in-time market context; news, macro and calendar context with declared
visibility assumptions; the cost model calibrated from broker terms; shadow
positions with tick-level exits, static and mirrored comparisons; the
deterministic limit check that rejects rather than adjusts; the free-rule
baselines in every report; the OpenAI Responses and Anthropic Messages adapters
with a hard budget; the opt-in WAIT scheduling (`--honour-wait`).

Fixed during the work: a run-ID collision when two runs started in the same
second; model answers with overlong free text rejected as invalid; the
instructions' phrasing of the weekend limit (now a neutral user limit, enforced
by the check, never by shortening the horizon).

Limitations: GDELT headlines are low-grade and arrive after the move; no
real-time professional newswire with first-seen times; no sentiment history; no
release times or consensus figures; the swap markup is today's applied to past
dates; replay cannot see slippage or requotes; one position per symbol and no
position sizing, so there is no equity curve, drawdown or Sharpe ratio, only R.

## 7. What would change the conclusion

- **Inputs with information the price does not have yet.** The only LLM
  hypothesis still open is interpretation of fresh information: an actual
  release against consensus in the first minutes, a statement's wording, or
  live positioning. That needs data LedgerQuant does not have today: release
  times and consensus figures, a newswire with first-seen times, and a sentiment
  history (now being captured live from 8 October 2026). Until then, more replay
  weeks on the present context recipe are not worth their cost.
- **Jev cannot supply direction.** Validation and scenario analysis over two
  analysts that agree with momentum 85 % of the time can reduce losses (as
  Claude's caution did in the Fed week) but not create an edge. Building Jev
  before the inputs change would test risk reduction, not edge.
- **Prospective evidence is the final judge.** The shadow pipeline on live data
  costs about 0.014 USD per GPT decision and removes hindsight; it is the right
  place to evaluate any changed recipe, after a replay has shown it beats the
  free rules.

## 8. Reproduction

```bash
# A week, GPT analyst/4 (hourly polling; add --honour-wait to skip calls during a WAIT)
PYTHONPATH=src .venv/bin/python -m ledgerquant.replay.run --start 2025-10-13 --end 2025-10-18 --cost-cap 5
# The same week on Claude Opus 4.6
PYTHONPATH=src .venv/bin/python -m ledgerquant.replay.run --profile configs/models/anthropic_opus46.profile.json \
  --start 2025-10-13 --end 2025-10-18 --cost-cap 30
# Report with free-rule baselines
PYTHONPATH=src .venv/bin/python -m ledgerquant.replay.report data/replay_runs/<run>
```

The decomposition in Section 4 comes from the scripts in
`tools/replay_analysis/` (see its README), which read finished run directories
and the archive without model calls.
