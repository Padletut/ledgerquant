# LedgerQuant Architecture

**Version:** 3.0 · **Date:** 10.10.2026

**Status:** Target design. Implemented today: live broker capture (ticks and
cTrader sentiment), the historical tick exporter, an OpenAI model adapter and a
manual, non-trading shadow Executor (`shadow_executor/2`). Everything else in
this document is target state; [Section 10](#10-current-state-and-build-order)
lists what exists.

Version 3.0 replaces the 2.x architecture. The 2.x track built research-process
governance around fixed price diagnostics, which was not the intended product.
Its code and documents are preserved under the git tag
`archive/research-governance-v1`. Change history lives in git, not in this file.

## 1. Mandate

LedgerQuant is a **multi-agent CFD trading system**. It is not rule-driven.

| Question | Answer |
| --- | --- |
| Who analyzes the market? | GPT and Claude agents, independently. |
| Who finds setups? | The agents themselves. |
| Who decides `LONG`, `SHORT`, `WAIT` or `NO_SIGNAL`? | The agents: GPT and Claude propose, Jev validates and makes the final decision. |
| Who protects capital? | The independent Risk Engine: deterministic code with user-set limits, not a model. |
| What does Research do? | A process the user starts, as a single run or continuously until a time, cost or outcome limit, to make the agents better traders. |

Consequences:

- Trading decisions come from agent judgement over market context. Fixed price
  rules are allowed only as **baselines** to compare agents against, never as
  the product.
- `NO_SIGNAL` is a normal, first-class outcome. An agent may abstain without
  inventing a setup or a justification.
- `WAIT` means a setup may be forming but something it depends on has not
  happened yet. It states what it waits for and when to look again.
- GPT and Claude do not need to agree. Disagreement is information for Jev and
  for Research.
- The agents also manage open positions: `HOLD`, `CLOSE` or an `ADJUST` of stop
  or target. Deterministic code protects capital but does not take over the
  agents' trading role.
- Agents propose and decide; they never hold broker authority. Position size,
  limits and the final veto belong to the Risk Engine and the broker-side
  execution cBot, under settings only the user controls.
- Research changes the agents (instructions, models, context, tools, roles,
  memory). It does not search for static trading rules.
- Agents are not deterministic. The same context can give a different answer;
  LedgerQuant records what the agents actually answered and never expects them
  to repeat it.
- Initial instruments: **EURUSD, GBPUSD and XAUUSD**.

## 2. Decision pipeline

One **decision cycle** runs for a point in time `T`. A clock triggers cycles on a
schedule. The clock is not a signal: it only decides *when* agents look, never
*what* they conclude. The same pipeline runs live (shadow, demo, live) and in
historical replay; only the context source differs.

```text
 clock ─► Context (point-in-time at T, enabled accounts and instruments only)
              │
              ▼
          Scout ───────────────► shortlist (may be empty → cycle ends, recorded)
              │   + instruments on the WAIT watchlist that are due
              │   + every open position (always reviewed, never screened out)
              ▼
     ┌────────┴────────┐
   GPT analyst     Claude analyst     each: news + sentiment + chart → proposal
     └────────┬────────┘              (NO_SIGNAL │ WAIT │ LONG/SHORT + setup)
              ▼
          Jev: validate ─────────► risk checks, scenario analysis,
              │                    final decision: NO_SIGNAL │ WAIT │ LONG/SHORT
              │                    (open position: HOLD │ CLOSE │ ADJUST)
              ▼
          Risk Engine (code) ────► per account: REJECTED(reason) │ APPROVED(size)
              │
              ▼
          Execution: shadow → demo → live (broker-side cBot enforces limits)
              │
              ▼
          Journal: every input, output, cost and outcome of the cycle
```

### 2.1 Context

Context is assembled for time `T` and contains only information whose
`available_at` is at or before `T`. Each source in the context has an explicit
status: `READY`, `STALE` or `UNAVAILABLE`. A missing source is shown as missing,
never filled with a guess or zero.

| Source | Content given to agents |
| --- | --- |
| Market | Recent bid/ask, derived bars at several timeframes, spread, session state |
| News | Headlines/articles and macro releases with their timestamps and source IDs |
| Sentiment | cTrader buy/sell percentages where recorded; other sentiment sources when added |
| Calendar | Scheduled macro events near `T` |
| Portfolio (read-only) | Open positions, exposure and remaining risk budget per account |

The universe is the set of instruments the user has enabled on enabled
accounts (Section 3). For the global pipeline it is the admin's instruments plus
every instrument a global-signals user has enabled (Section 9.2). Deterministic **data-quality** filters run before the
Scout: an instrument with a closed market, stale feed or invalid quotes is marked
unavailable. These filters say nothing about direction and are not trading
rules.

### 2.2 Scout

The Scout sees a compact summary of every available instrument in the universe
and returns a short **shortlist** with one line of reasoning per pick. Most
instruments are dropped, and an empty shortlist is normal. The Scout is an agent
(a cheap GPT/Claude model or Jev `Choice` questions), not a threshold screen.
Instruments on the `WAIT` watchlist whose recheck time has come are added to the
shortlist directly.

### 2.3 Analysts: GPT and Claude

For each shortlisted instrument, a GPT analyst and a Claude analyst run
independently and in parallel. Each sees the full context, but not the other's
output. Each returns a typed `Analysis`:

- a view per perspective (news, sentiment, chart): `BULLISH`, `BEARISH`,
  `NEUTRAL` or `NO_VIEW`, with key points citing context IDs;
- a **proposal**: `NO_SIGNAL` (nothing required), `WAIT` (what it waits for and
  when to look again), or `LONG`/`SHORT` with a setup: thesis, cited context
  IDs, entry (at market, or a pending order with price and expiry), stop
  (invalidation level), target or horizon, and what it is
  unsure about.

A perspective whose source is `UNAVAILABLE` is `NO_VIEW`; the analyst does not
guess. Analysts propose stop levels, not position sizes. Splitting the
perspectives into separate specialist agents is a variant Research can test.

### 2.4 Jev: validation and final decision

Jev is a typed decision model. It answers versioned questions over a typed state
built from the context summary and both analyses: `Choice` selects among
declared options, `Score` rates against a declared rubric and `Noul` returns a
probability for a yes/no proposition. Jev is called when at least one analyst
proposes `WAIT`, `LONG` or `SHORT`; if both propose `NO_SIGNAL`, the cycle
records `NO_SIGNAL` without a Jev call.

- **Risk checks:** judgement questions about each proposal, such as whether the
  stop sits beyond the risk the analyst named, or whether a scheduled event
  inside the horizon threatens the setup.
- **Scenario analysis:** questions such as the probability that the stop is hit
  before the target within the horizon, for each proposal.
- **Final decision:** a `Choice` among options built from the proposals, for
  example *GPT's LONG setup*, *Claude's SHORT setup*, `WAIT` or `NO_SIGNAL`.

Jev chooses among the proposals; it does not invent entry or stop levels. When
the analysts disagree, Jev may follow one, wait or abstain. All of Jev's answers
are recorded with the decision. Jev's risk checks are judgement; the hard capital
limits remain in the Risk Engine.

### 2.5 WAIT and the watchlist

`WAIT` means: there may be a trade here, but the agents need **new information
or a judgement they cannot make yet** before deciding. A `WAIT` is a request for
a new analysis, never a deferred order. It always states what it waits for and
when to look again.

| Waits for | Example |
| --- | --- |
| `EVENT` | A scheduled release or announcement: after CPI at 12:30 UTC, after the central-bank statement |
| `CONFIRMATION` | Price behaviour that needs judgement: whether a breakout holds through the London open, how price reacts at a level |
| `CONDITIONS` | Tradable conditions: spread back to normal after rollover, volatility settling after a spike |
| `CLARITY` | Conflicting evidence that new data may resolve, for example GPT and Claude disagreeing |

If the condition is only a price level ("buy if price breaks 1.0950"), it is not
a `WAIT`: the agents place a pending order, which the broker can execute without
them.

A `WAIT` puts the instrument on a watchlist. It is rechecked at the earliest of
its recheck time, a stated delay after the awaited event, or a price alert level
being touched; an alert triggers a new analysis, not an order. At recheck the
instrument goes straight to the analysts, with the earlier `WAIT` in its context.
A `WAIT` expires at its recheck time if no new decision is made; waiting again
requires a new decision.

### 2.6 Risk Engine

The Risk Engine is deterministic code. No agent can change or bypass it. It
decides what is allowed, the maximum exposure and when a position must be
force-closed. It does not choose entries or exits; that is the agents' role.

For each final `LONG`/`SHORT` decision it checks **per enabled account**
against the user's settings (Section 3) and returns `APPROVED` with a
computed size, or `REJECTED` with a typed reason. Checks include:

- account and instrument enabled;
- fresh account state from the broker adapter; if it is stale or unavailable,
  new entries on that account are rejected;
- a stop is present and respects the broker's minimum stop distance;
- risk per trade and combined portfolio risk;
- margin per trade and the minimum free margin;
- exposure per instrument, currency and correlated group;
- daily and weekly loss limits;
- current spread and quote freshness at execution time;
- broker symbol constraints such as minimum volume and step.

The Risk Engine **never changes the stop or target an agent has set.** It
sizes the position from the agent's stop and then approves or rejects; it does
not move, tighten or widen levels.

For an open position or pending order, a `CLOSE` is always allowed. An `ADJUST`
is approved when the position with the new levels still fits the user's
per-trade risk, portfolio risk and margin; otherwise it is rejected and the
position keeps its current stop and target. The Risk Engine **force-closes** a position, whatever the agents say, when its maximum holding
time is reached, a loss limit is breached, or free margin falls below the
user's minimum.

The Risk Engine protects capital. It does not judge whether a setup is good; that
is the agents' job, and Research measures it.

### 2.7 Open positions

Responsibility is split three ways:

| Who | Decides |
| --- | --- |
| Agents (GPT, Claude, Jev) | Entry (at market or pending), `HOLD`, `WAIT`, `CLOSE` and proposed adjustments of stop, target or pending entry |
| Risk Engine | What is allowed within the user's risk limits, maximum exposure and when a position must be force-closed; never changes the agents' stop or target |
| Broker | Stop-loss and other supported protective orders that hold if agents, LedgerQuant or the API are unavailable |

Every open position, real or shadow, is reviewed in every cycle. GPT and Claude
each see the context, the position (entry, current result, stop, target, time
open) and the original thesis and invalidation, and propose `HOLD`, `CLOSE` or
`ADJUST`. Jev validates and decides among the proposals, as for entries, and the
Risk Engine checks the result. If both analysts propose `HOLD`, the position is
held without a Jev call.

The horizon set at entry is a **maximum holding time**: a safety limit enforced
by the Risk Engine, not the only allowed exit. The agents may close earlier.
Position review runs from the first shadow version, where a close or adjustment
changes a shadow position and no real order. This is what lets Research measure
whether GPT, Claude and Jev manage positions better than a static exit.

### 2.8 Pending orders

A setup may enter with a pending limit or stop order instead of at market. A
pending order is never left open-ended: it must be handled or expire.

- Every pending order has an expiry no later than the user's maximum
  pending-order lifetime. The broker order carries the same expiry, so it lapses
  even if LedgerQuant is down.
- While pending, it counts against the reserved trade slots and the per-trade
  and portfolio risk as if it were filled.
- It is reviewed in every cycle like an open position: `HOLD` keeps it, `CLOSE`
  cancels it, and `ADJUST` moves entry, stop or target, subject to the same
  risk check as an open position.
- An order that reaches its expiry unfilled is recorded as `EXPIRED`. In shadow
  mode a fill is simulated when the quote reaches the entry price.

`WAIT` and a pending order differ: `WAIT` places nothing and asks the agents to
look again, while a pending order is a committed entry at a stated price.

### 2.9 Execution

Execution has three modes, adopted in order: **shadow** (record only, no orders),
**demo** (broker demo account) and **live**. A separate execution cBot on the
broker side places the protective stop with every entry and enforces account
limits even when LedgerQuant, models or the network are down. The market-data
cBots never expose trading operations. A broker acknowledgement is not a fill,
and an uncertain order state is reconciled before any retry. The user can
always close a position manually.

**Partial fills.** An order can fill only partly. Risk, margin, later `ADJUST`
checks, closing and results all use the **actual filled volume** reported by the
broker, never the proposed volume. Reserved risk for an unfilled remainder stays
reserved while the remainder is still pending and is released when it is
cancelled or expires.

### 2.10 Journal

Every cycle is recorded append-only: the context snapshot (or its hash and
source references), each agent's exact input, output, model, version and cost,
Jev's answers, the Risk Engine verdict per account, execution events and, later,
the outcome. The journal is what Research learns from and what the user
reviews.

## 3. User settings

The user sets the boundaries the Risk Engine enforces. Every control below is
designed to be operated simply from the console when it is built. Until
then the same settings live in a versioned configuration file. Every change is
versioned, logged with its time and applies from the next cycle. Agents can read
the resulting limits but never change them.

Account state (balance, equity, free margin, margin in use, open positions and
pending orders) is **read from the broker** through the broker adapter: the cBot
now, a broker API later. The user never enters it; the console shows it
read-only with the time it was last updated.

| Control | Meaning |
| --- | --- |
| Accounts | Each broker account, demo or real, is enabled or disabled for trading individually. This is the only switch between demo and real trading. A newly added account starts disabled. Disabled means no new trades; open positions stay protected and are still reviewed by the agents until closed. |
| Instruments per account | Which of the account's broker symbols may be traded on that account. |
| Portfolio risk | Maximum combined loss at the stops of all open positions, as a percentage of equity. |
| Minimum free margin | The lowest free margin the account may reach, as a percentage of equity. |
| Reserved trades | `N` trade slots. Each new trade may use at most `1/N` of the portfolio risk, and at most the margin above the minimum free margin divided by the slots still free. |
| Loss limits | Daily and weekly loss limits. When breached, no new trades open and open positions are force-closed. |
| Maximum holding time | The longest a position may stay open; an agent's horizon cannot exceed it. |
| Maximum pending-order lifetime | The longest a pending order may stay open before it expires. |

**Reserved-trades example** (illustrative numbers): equity 10,000, portfolio risk
3 % and `N = 3` give at most 100 at risk per trade. With free margin 9,000 and a
minimum free margin of 40 % of equity (4,000), 5,000 is usable; with no open
trades, the first trade may use at most 5,000 / 3 ≈ 1,667 in margin. Three
trades can then be open without breaching the minimum. Equity, free margin and
the number of open trades come from the broker.

## 4. Agents and models

An **agent version** is the hashed combination of instructions, model profile,
tools, context recipe and output schema (for Jev: question set and options).
Changing any of them creates a new version, and earlier decisions keep the
version that produced them.

| Provider | Role | Notes |
| --- | --- | --- |
| GPT (OpenAI) | Analyst, Scout, Research | Adapter implemented (Responses API) |
| Claude (Anthropic) | Analyst, Scout, Research | Adapter target. Opus 4.6 for replay track 1, Sonnet 5.5 for track 2; Haiku 5.5 is a cheaper Scout option |
| Jev (TypeSafe) | Validation and final decision; Scout option | Typed `Choice`, `Score`, `Noul`; text input only; adapter target |

Which model fills which role is configuration. Each model profile records its
**published training cutoff**; replay depends on it (Section 5.2). Provider
fallback is explicit and versioned; a live deployment never silently switches
model.

**Agents are not deterministic.** The same context can produce a different
answer on another call. The journal records the answer that was actually given
and acted on. Running a past point again with fresh inference produces a new
sample, not a reproduction, and is labelled as such. Determinism is required only
of the code around the agents: context assembly, the Risk Engine and execution.

## 5. Research: making the agents better traders

### 5.1 Research runs

Research is a process the user starts, from the command line now and from
the console later. It runs in one of two modes:

- **Single run:** one round of proposals and tests, then a report.
- **Continuous run:** repeated rounds, each learning from the previous round's
  results, until a stop condition is met: a time limit, a cost limit or an
  outcome (for example a candidate beats the current variant by a stated margin
  on the development window, or a stated number of rounds without improvement).
  The user can stop it at any time.

When starting a run, the user chooses:

- the pipeline variant to improve;
- the journal period to learn from;
- the replay window to test on, after the models' training cutoffs;
- whether the holdout may be used, once, at the end of the run;
- a model spending limit, and for a continuous run its stop conditions.

Each round proceeds:

1. A Research agent reads the journal and earlier rounds: wins, losses,
   abstentions, waits, pending orders, position management, disagreements
   between GPT and Claude, Jev's choices, Risk Engine rejections and forced
   closes.
2. It proposes concrete changes (instructions, models, context, tools, roles,
   Jev questions), each as a candidate variant with what it should improve.
3. Each candidate and the current variant are replayed on the same decision
   points and compared with each other and with baselines.

The run ends with a report. The user adopts a candidate or discards it. A
research run never changes a running variant or the user's settings, and it
never adopts a candidate by itself. Many rounds on the same development window
make overfitting to it more likely, which is why the holdout stays outside the
loop.

### 5.2 Historical replay

The replay engine reconstructs the context at past times `T` from archived
data, honoring `available_at`, and runs a variant through the full pipeline,
Risk Engine included, in shadow mode.

**Training-cutoff rule.** A model may already know what happened after `T` if
`T` is before its training cutoff. A replay window used for performance claims
therefore starts **after the latest published training cutoff of every model in
the variant**. Earlier windows may be used only to debug the pipeline; their
results are labelled `CONTAMINATED` and never used to rank variants. A published
cutoff is a lower bound, not a guarantee of clean data.

This rule makes post-cutoff data the scarce resource (Section 6). New models
with later cutoffs shrink the usable window, which is why continuous capture
matters. The rule uses the **training data cutoff**, which is later than or equal
to the reliable knowledge cutoff, and every model profile records it. Cutoffs are
not available from provider APIs; they come from the providers' published model
documentation.

**Replay tracks.** Because current models have recent cutoffs, replay runs in two
tracks that share one holdout:

| Track | Models | Training data cutoff | Development window |
| --- | --- | --- | --- |
| 1. Long history | GPT-5.4 mini and Claude Opus 4.6 | Aug 2025 (both) | 1 Sep 2025 – 31 Aug 2026 |
| 2. Current models | GPT-5.4 mini and Claude Sonnet 5.5 | Jun 2026 (Sonnet 5.5) | 1 Jul 2026 – 31 Aug 2026 |
| Holdout (both) | | | 1 Sep 2026 – 8 Oct 2026 |

Track 1 has a long, clean history and is where the pipeline, instructions and
context recipes are developed. Its results hold for those models; they do not
carry over to newer ones. Track 2 evaluates the models intended for live use on
their own clean window and in prospective shadow. A model with a cutoff later
than June 2026 shrinks track 2 further. Jev's training cutoff is not yet known
and must be recorded before Jev enters a ranked variant.

**Replay settings.**

- **Decision cadence:** one decision cycle every hour on the hour, 07:00–20:00
  UTC on trading days (the London and New York sessions), for EURUSD, GBPUSD and
  XAUUSD. The cadence is variant configuration.
- **Backfilled broker ticks:** exported ticks have no real `available_at`; replay
  treats each as visible at its event time. This is a declared assumption, so a
  replay over exported ticks is a retrospective simulation, labelled as such, and
  never reported as live performance.
- **Backfilled news visibility:** GDELT items backfilled without a real
  `available_at` count as visible 15 minutes after their GKG batch time. This is
  a declared assumption, recorded with every replay that uses it. Live-captured
  items use their real `available_at`.
- **Macro vintages:** an ALFRED value is visible from the start of the UTC day
  after its `realtime_start` date, because release times are not recorded.
- **cTrader sentiment:** `UNAVAILABLE` before 9 October 2026.

### 5.3 Scoring

Each decision is scored after its horizon has passed:

- **Trades:** simulated net P/L with spread and costs, maximum adverse and
  favorable excursion, and whether the stop or target was hit.
- **Abstentions:** what would have happened. Abstaining on a market that went
  nowhere is good; missing a clean move is a measured opportunity cost.
- **Waits:** whether the awaited condition happened, and whether the later
  decision was better than acting immediately.
- **Pending orders:** how often they filled or expired, and whether a filled
  order beat entering at market at decision time.
- **Position management:** the agents' `HOLD`/`CLOSE`/`ADJUST` decisions against
  a static exit on the same positions (hold to stop, target or maximum holding
  time). This tests whether the agents manage open positions better.
- **Process:** disagreement between analysts, Jev's choices, Risk Engine
  rejections, invalid outputs, unsupported citations, latency and model cost.

Variants are compared on the same points. Baselines (always `NO_SIGNAL`, random
entries with the same risk, simple fixed rules and static exits) show whether
the agents add anything.

### 5.4 Avoiding self-deception

- Keep a **holdout** part of the post-cutoff window untouched while proposing and
  choosing variants. Evaluate the chosen variant on it once. The current holdout
  is 1 September – 8 October 2026 (Section 5.2); after it has been used, new
  evaluation is prospective.
- Record every variant tried, including failures.
- Because agents are not deterministic, compare variants over enough decision
  points and, where it matters, run the same points several times. Report the
  spread of results, not only the average.
- The final judge is **prospective** evidence: the shadow pipeline on live data,
  where hindsight is impossible.

### 5.5 Promotion ladder

`replay` → `shadow` (live data, no orders) → `demo account` → `live, small size`.
The user approves each step; a variant moves up only with evidence from the
step below.

## 6. Data

| Data | Historical | Live capture | Note |
| --- | --- | --- | --- |
| Broker ticks (IC Markets via cTrader) | Exportable through the cTrader CLI tick exporter; 2020 coverage sampled | Since 9 Oct 2026, ~100 symbols | Post-cutoff windows not yet exported |
| cTrader sentiment | **None**: real-time only | Since 9 Oct 2026 | Sentiment cannot be replayed before capture began |
| News | GDELT GKG backfill from 1 Sep 2025 running, labelled backfilled | Since 10 Oct 2026: GDELT GKG (FX and gold scope) and Fed, ECB and BoE releases, with real `available_at` | No economic calendar yet ([NEWS.md](operations/NEWS.md)) |
| Macro releases | ALFRED vintages from 1 Sep 2025 for 14 tracked series | Since 11 Oct 2026: FRED release calendar and ALFRED vintages | Release dates have no time of day; no policy-meeting calendar yet |

Data needed for post-cutoff replay:

1. **Export broker ticks** for EURUSD, GBPUSD and XAUUSD from the earliest relevant
   training cutoff to today, using the existing tick exporter.
2. **Live news capture** records when each item arrived (running since 10 October
   2026). The post-cutoff window is back-filled from GDELT, labelled as
   backfilled. Macro data and its release calendar come from FRED/ALFRED; a
   calendar of policy meetings and release times is still missing.
3. **Keep capture running continuously.** Every day adds clean, post-cutoff,
   point-in-time data, including sentiment that can never be back-filled.
4. In replay, a source that did not exist at `T` is `UNAVAILABLE`, and the
   analysts' view for that perspective is `NO_VIEW`.

Detailed measurements are in [DATA_AVAILABILITY.md](data/DATA_AVAILABILITY.md).

## 7. Failover

An agent, a model provider, LedgerQuant itself or a connection can fail at any
time. Failover keeps open positions and pending orders protected and managed
without closing everything, and without letting a partial analysis open new
risk.

### 7.1 Principles

- **Protection never depends on the agents.** Every position has its stop (and
  target, if set) at the broker from the moment it opens, and every pending
  order carries its expiry at the broker. These hold even if every agent and
  LedgerQuant are down.
- **A failure closes nothing by itself.** Positions are closed by their stop,
  target, the agents, the user's own limits or the user, never just because a
  component is unavailable.
- **A completed decision stays valid until its expiry.** Executing a decision
  never needs the agents again.
- **New risk needs a complete decision.** Missing analyses lead to no new entry,
  not to a guess.
- **Every degraded state is recorded and shown to the user.** A decision made in
  degraded mode is labelled as such in the journal and on the performance page.

### 7.2 Decisions already made

| Decision | Valid until | Executes without the agents? |
| --- | --- | --- |
| Approved entry at market | Its decision expiry | Yes. The Risk Engine checks it again at execution time. |
| Pending order | Its expiry | Yes. It is held at the broker and fills there. |
| `WAIT` | Its recheck time | No. A `WAIT` places nothing; acting on it needs a new decision. |
| Open position | Until closed | It stays open and protected. Reviews need the agents (Section 7.3). |

A `WAIT` that all agents agreed on stays valid as a `WAIT` until its recheck
time, but it contains no order. When the agents can already state the level,
stop and target at which they would act, they place a **pending order** instead:
it is then executable on its own, even if the agents later fail. If the agents
are unavailable at a `WAIT`'s recheck time, the `WAIT` expires without an entry.

### 7.3 When an agent fails

An agent counts as unavailable for a cycle when its call fails, times out or
returns invalid output before the cycle deadline. An analysis call has no side
effects, so it may be retried once within the deadline; both attempts are
recorded. A provider that keeps failing is marked down and retried on later
cycles. A variant may declare an explicit fallback model per role; using it is
recorded as degraded and is never a silent switch.

| Unavailable | New entries | Open positions and pending orders |
| --- | --- | --- |
| One analyst (GPT or Claude) | Allowed only if the variant permits single-analyst entries (`min_analysts_for_entry`, default 2); Jev then sees that one analysis is missing | Reviewed with the remaining analyst and Jev |
| Jev | None: there is no final decision | An action is applied only if both analysts propose the same `CLOSE` or `HOLD`; otherwise `HOLD` |
| Both analysts | None | `HOLD`; broker protection and the user's limits still apply |
| All models | None | `HOLD`; broker protection and the user's limits still apply |
| Market data stale | None | `HOLD`; agents never decide on stale data |

In every row the Risk Engine still force-closes on the user's limits, approved
entries and pending orders remain valid until their expiry, and the user can
close a position manually.

### 7.4 When LedgerQuant or a connection fails

- **LedgerQuant or the control API down:** stops, targets and pending expiries
  hold at the broker. The execution cBot keeps a local copy of each position's
  maximum holding time and the account's loss limits and minimum free margin,
  and enforces them itself when it loses contact with LedgerQuant (missed
  heartbeats). It opens nothing new on its own.
- **Execution cBot disconnected or restarted:** LedgerQuant sends it no orders
  and marks the account degraded. Events wait in the database. A disconnect or
  restart **never closes or cancels anything by itself**: there is no "close all
  on disconnect". Positions and orders stay at the broker with their protection.
- **cBot reconnect or restart:** LedgerQuant decides what is still valid; the
  broker shows what actually exists. The cBot reports the broker's positions,
  orders and fills, and LedgerQuant reconciles them with its own state. Each
  position and order is matched by the LedgerQuant ID it carries at the broker
  and adopted again, with its stop, target, maximum holding time or expiry from
  LedgerQuant. A cBot that lost its local state reloads it from LedgerQuant; it
  never treats a LedgerQuant position or order it no longer remembers as an
  orphan to close. A position or order at the broker that LedgerQuant did not
  create, such as a manual trade, is left untouched and shown to the user.
  Anything that closed at the broker meanwhile, for example by its stop, is
  recorded from the broker's fills.
- **On reconnect:** broker positions, orders and fills are reconciled with the
  journal before anything new happens. A position or order that is **still
  valid is kept**, never closed just because of the outage; only what is no
  longer valid is closed or cancelled (see below). Idempotency keys ensure that
  nothing executes twice.

**Validity after a reconnect.** A pending order is valid while it has not
expired and still fits the user's limits. An open position is valid while it is
within its maximum holding time, the user's limits are not breached and, for a
global signal, the signal is still open. Anything no longer valid is closed or
cancelled; everything still valid stays as it is.

Events that waited during the outage are agent decisions made on the context of
their time. Each carries a decision expiry, like an entry:

- An event still within its expiry is processed in sequence: a `CLOSE` or
  cancellation is applied, and an `ADJUST` or entry is checked by the Risk Engine
  against the current state.
- An event past its expiry is dropped, whether it is an entry, `ADJUST`, `CLOSE`
  or cancellation. The affected position or order is reviewed by the agents in
  the next cycle with fresh context instead.
- **Risk Engine unavailable:** nothing new executes. Broker protection holds,
  and the cBot enforces its local limits.

### 7.5 Stale commands and races

Reconciliation is a snapshot. The broker's state can change between
reconciliation and execution: a stop can be hit, a pending order can fill, a
position can be closed manually. Every command is therefore checked against the
broker's actual state at the moment it executes, not only at reconciliation.

Example: GPT proposes `CLOSE`, Claude proposes `HOLD`, Jev chooses `CLOSE`, the
connection drops, the position hits its broker stop, the connection returns, and
the old `CLOSE` is still queued. The system must see that the position is
already closed, record the actual outcome and send no new order.

- **Commands target a broker ID and carry the expected state.** A `CLOSE` names
  the position ID and expects it to be open; a cancel names the order ID and
  expects it to be pending; an `ADJUST` names the position or order and the
  state it was decided on.
- **The cBot checks right before sending.** The cBot sees the live broker state.
  If the target no longer exists or no longer matches (closed, filled, already
  cancelled), it sends nothing and reports the command as `STALE` together with
  the actual state.
- **Close and cancel act only by ID.** A `CLOSE` closes that position, never by
  sending an opposite market order, which could open a new position if the
  original is already gone. A failed cancel because the order has just filled
  is never turned into a close; the filled position becomes an open position for
  the agents to review in the next cycle.
- **One queue per account in the cBot.** Broker events (fills, closes, stop hits)
  and LedgerQuant commands are processed in one sequence per account, so a
  command never acts on a state the cBot has already seen change.
- **Idempotency at the broker.** Each command's ID travels with the broker order
  (label or comment), so a repeated command is recognised and not executed
  twice. A result that remains uncertain, such as a timeout, is reconciled
  before anything else is sent.
- **Both the decision and the outcome are recorded.** In the example the journal
  keeps Jev's `CLOSE` as decided but not executed (`STALE`: already closed), and
  the trade's exit reason is the broker stop. Research can then compare what the
  decision would have achieved with what happened.
- **A pending order filled while disconnected** is recorded from the broker's
  fill. It is now an open position with the stop and target attached to the
  order. Queued commands for the pending order (cancel, entry adjustment) become
  `STALE`; the position is reviewed in the next cycle.

### 7.6 Global signals

If the global pipeline fails, users on global signals keep their positions under
broker protection and their own limits, and are notified that no new signals
arrive. Open global signals follow Section 7.3: without agent reviews they are
held. If a user's own cBot is disconnected, the rules in Section 7.4 apply to
that user's accounts only.

### 7.7 Testing failover

Failover is tested in shadow and on a demo account before live trading: a
provider outage, Jev unavailable, LedgerQuant stopped, a cBot disconnected
during an open position and a pending order, and stale market data. Race tests
include a stop hit while a `CLOSE` is queued, a pending order filling while the
cBot is disconnected, a state change between reconciliation and execution, a
partial fill, and one global `CLOSE` reaching accounts in different states.
Each test checks that protection held, nothing was closed without cause, nothing
executed twice, no opposite order was opened and the journal shows both the
decision and the actual outcome.

## 8. Safety and integrity rules

- Agents never call broker trading APIs. Only the execution path does, after the
  Risk Engine.
- Accounts, instruments and risk limits are user settings.
  Agent output and research runs cannot change them.
- Source text (news, retrieved documents) is data, never instructions.
- Every model call records its exact input, output, model version and cost. Each
  run has a spending limit.
- Live context and replay context are labelled as such; a replay is never
  reported as live performance.
- Credentials stay in ignored files and secrets now, and in an encrypted
  per-user secret store on the platform; they never enter model input, logs or
  the journal.

## 9. Platform: users, access and console

This is target state, built together with the console. Until then LedgerQuant
runs as a single-user deployment.

### 9.1 Users and roles

There is one kind of person on the platform: a **user**. A user trades their own
broker accounts with their own settings. The **admin** is a user who also has
platform rights. In the single-user deployment, the one user is also the admin.

| Role | Can |
| --- | --- |
| Admin | Register, disable and remove users; manage global credentials; decide which users may receive global signals; cap the global pipeline's instruments and model spending; operate the **global pipeline** with all its functions (variants, model roles, schedule, its own instruments, research runs and its journal); set platform limits |
| User | Manage their own accounts, instruments, risk settings and, in their own pipeline, variants and research runs; review their own journal |

Each user's accounts, settings, positions, journal and research runs are separate.
The admin cannot see or change another user's trading. Only the user can grant
the admin access to their trading, and can withdraw that access at any time.
Every change, grant and withdrawal records which user made it.

### 9.2 Own pipeline or global signals

Each user trades in one of two ways. The admin decides which users may choose
global signals.

| | Own pipeline | Global signals |
| --- | --- | --- |
| Who runs the agents | The user's own pipeline | The admin's global pipeline |
| Model credentials (OpenAI, Anthropic, Jev) | The user's own | None; the user registers no model keys |
| Model cost | The user's | The global pipeline's |
| Research runs | The user's own | Run by the admin on the global pipeline |
| Broker accounts and credentials | The user's own | The user's own |
| Risk settings and Risk Engine | The user's own | The user's own |

A global signal is the lifecycle of one global decision: entry (with setup,
stop, target, maximum holding time and, for a pending order, its expiry), then
`ADJUST`, `CLOSE` or cancellation. The global pipeline's agents manage a
reference position per signal, and each event carries the signal ID and a
sequence number.

For a user on global signals:

- The user's instruments decide what they receive: signals for every instrument
  they have enabled on an enabled account. The admin's instrument choice never
  restricts them. The global pipeline covers the admin's instruments plus every
  instrument a global-signals user has enabled, within the admin's cap below.
- This holds as long as the platform has data for the instrument, meaning a live
  market-data feed for it. An instrument without data is shown to the user as
  unavailable and is not traded.
- The user's Risk Engine checks and sizes every entry with the user's own
  settings, per account. An entry it rejects is not taken, and later events for
  that signal do not apply to that account.
- A `CLOSE` is always applied. An `ADJUST` that would take the position outside
  the user's risk limits is rejected for that account; the position keeps its
  current stop and target.
- The user's own limits still force-close positions, whatever the signal says.
- A signal that arrives too late to act on, past the maximum signal age, is not
  entered.
- The global pipeline analyzes each instrument **once per cycle**, however many
  users receive its signals. Model calls grow with the number of distinct
  instruments, never with users × instruments. Applying a signal to each user's
  accounts is deterministic code in that user's Risk Engine and needs no model
  call.
- The admin can **cap** the global pipeline with a maximum number of
  instruments and a model spending limit per period. When users enable more
  instruments than the cap allows, the admin's own instruments are covered
  first, then those enabled by the most users. An instrument outside the cap is
  shown to the user as not covered by global signals.
- Reviews of open signals and pending orders come before new-entry analysis.
  As the spending limit approaches, new-entry analysis stops first, so open
  signals keep being reviewed; their broker stops protect them regardless.
- The performance page shows the user's own results separately from the
  reference results of the global signals.

**One decision, many account states.** The agents make one decision per global
signal; they are the same agents whether one user or many receive it. The code
around them tracks the signal's state **per account**, and every later event is
applied according to that account's own state. When Jev decides `CLOSE` on the
global XAUUSD position:

| Account | Actual state | What happens |
| --- | --- | --- |
| A | Position open | `CLOSE` is executed |
| B | Entry was rejected | Nothing; the signal never applied to this account |
| C | Broker stop already hit | `CLOSE` is recorded as already handled |
| D | cBot offline | `CLOSE` waits within its validity. If the cBot returns later, the position is no longer valid because its signal has ended, and it is closed on reconnect |
| E | User closed it manually | No new order |

A later `CLOSE` or `ADJUST` for a signal applies only to the position that
signal opened on that account, identified by its LedgerQuant ID. It never
affects another position on the same account, even on the same instrument.

### 9.3 Broker accounts and cBot authority

- **One owner per broker account.** A broker account (broker, environment and
  account number) can be registered by exactly one user. Registering an account
  that is already registered is refused, so two users or two pipelines can never
  steer the same position.
- **One pipeline per position.** An account follows either its user's own
  pipeline or global signals. If the user switches, positions and orders already
  open stay with the pipeline that opened them until closed; new entries come
  from the new choice.
- **cBot authority is explicit.** Each execution cBot has its own token bound to
  specific broker accounts. On connect and reconnect, LedgerQuant tells it which
  accounts, positions and orders it has authority over. The cBot acts only on
  those, and LedgerQuant rejects any command or report for an account the token
  is not bound to.
- **User isolation.** A user can never read, change or close another user's
  accounts, positions or orders without that user's explicit grant. Every query
  and command is checked on the server against the owner, not only filtered in
  the frontend, and this is covered by tests.

### 9.4 Credentials

- Broker credentials always belong to the user.
- Model-provider keys belong to the user in own-pipeline mode. Users on global
  signals have none; global model credentials are used only by the global
  pipeline.
- Credentials are stored encrypted in a secret store. The frontend can set or
  replace them but never shows them again. They never appear in logs, the
  journal or model input.

**Account identifiers.** A broker login (such as the cTrader ID or e-mail) is a
credential and follows the rules above. A broker account number is an
identifier, not a secret, but it is personal and must not spread:

- The account number is stored **once**, encrypted, in the account registry,
  together with the owner, broker, environment and a label the user chooses.
  Everything else (capture, journal, positions, manifests, logs) refers to the
  account by its internal LedgerQuant account ID.
- Where a lookup by number is needed, for example to match a cBot report to its
  account, a keyed hash of the number is stored next to the encrypted value, so
  matching never requires decryption.
- Encryption and hashing happen on the server with keys from the secret store.
  The connection from a cBot is already protected by TLS; a cBot does not hold
  encryption keys. It sends the number once when it registers or reconnects and
  otherwise uses the account ID it receives.
- The frontend shows the user's label and a masked number (for example
  `•••2334`), only to the account's owner. The full number and the login are
  never sent to the browser after they have been entered.
- Logs never contain a login or a full account number. Output from tools we do
  not control, such as the cTrader CLI, is redacted before it is stored.

Current state: the live capture tables, TickExport manifests and cBot logs still
hold account numbers in plain text in the private database and the ignored
`data/` directory. Moving them to account IDs needs a new capture contract and a
migration of the existing append-only capture rows; it is done together with the
account registry.

### 9.5 Signal delivery

Every signal event and execution instruction is first written to the database,
which is authoritative, and then pushed over WebSocket to connected clients:
execution cBots and open consoles. Each message carries an ID and sequence
number. A client that reconnects resumes from the last sequence it confirmed, so
a dropped connection loses nothing; execution stays idempotent, so a repeated
message never creates a second order.

A single FastAPI instance holds all connections at first. Only when measured
load needs more than one instance is a shared message layer added (for example
Redis Streams), so that any instance can deliver events to its own connections.
The message format and resume rule above make that change additive.

### 9.6 API security

- The browser talks only to the control API, never directly to PostgreSQL,
  broker or model-provider APIs.
- Authentication is built into the FastAPI backend and kept simple; no external
  identity provider. The admin creates users, and users sign in with username
  and password. Passwords are stored only as a slow hash (Argon2id).
- A signed-in user gets a server-side session in an `HttpOnly`, `Secure`,
  `SameSite` cookie, with an expiry and CSRF protection on changing requests.
  Every request is checked against the user, role and ownership of what it
  touches.
- Machine clients (capture cBots, execution cBots, workers) use their own API
  tokens, limited to what each client needs and stored as hashes.
- HTTPS only. Disabling a user ends their sessions and revokes their tokens.
- Two-factor sign-in (TOTP) can be added later without changing this design.

**Request limits** protect the API against spam without throttling normal
machine traffic:

- Sign-in attempts and other unauthenticated requests are limited strictly per
  client address. Repeated failed authentication blocks that address for a
  while with `429`.
- Authenticated users and machine tokens get their own limits. A cBot's limit is
  set well above its measured normal rate, so capture and execution are never
  throttled in normal operation.
- Request bodies and batches have size limits.
- The API sees the real client address only through the trusted reverse proxy
  (Caddy), never from an arbitrary forwarded header.
- A throttled client backs off and retries. Capture batches and execution
  messages are idempotent, so a retry is safe.

Current state: the capture API already requires a bearer token (compared in
constant time), limits bodies to 1 MiB and batches to 250 observations, exposes
no documentation endpoints and is reached over HTTPS through Caddy. Its token is
a plain secret file, not yet a stored hash, and it has **no rate limiting yet**.

### 9.7 Console

- **Mobile first:** designed for small screens first, then extended to tablet
  and desktop as a responsive web app.
- **Accessible:** meets WCAG 2.2 level AA: full keyboard use, screen-reader
  labels, sufficient contrast, text resizing, reduced motion, and no
  information carried by color alone (a `LONG`, `REJECTED` or stale status is
  also written as text).
- **Operational view:** it shows state from the API and computes nothing
  authoritative. Missing or stale data is shown as missing or stale, never as
  zero or example data.
- The controls in Section 3 are its core: simple to reach and change on a phone.

### 9.8 Performance and history

A separate console page tracks trading performance and history, including the
status of open trades and pending orders. It is kept apart from the user
settings.

**Filters:** account, instrument, period, mode (`shadow`, `demo`, `live`),
pipeline variant, which proposal Jev chose (GPT or Claude), status and exit
reason. Shadow, demo and live are never added into one total. Replay results
belong to research reports, not this page.

**Summary:** total trades (closed and open), win rate, net P/L from the broker,
account growth, average daily and weekly return, maximum drawdown in amount and
percent, CAGR, Sharpe ratio, profit factor, average win / average loss, average
realized R against the initial stop, longest win and loss streaks, edge stability
(share of rolling windows with positive expectancy), rolling expectancy and
rolling Sharpe over the last trades, and equity smoothness.

**Agents:** counts of `NO_SIGNAL`, `WAIT`, `LONG` and `SHORT`; how often GPT and
Claude disagreed and whose proposal Jev chose, with results for each; Risk Engine
rejections by reason; agent `HOLD`/`CLOSE`/`ADJUST` decisions on open positions.

**Breakdowns and curves:** results per instrument and per weekday; realized
balance curve (closed trades), equity curve including floating P/L, return
curve, daily return and drawdown curves; P/L distribution in pips and in R.

**Exit reasons:** agent close, stop-loss, take-profit, maximum holding time, Risk
Engine forced close (with its reason), manual close, reconciled and unknown.
Pending orders that expire unfilled are counted separately, not as trades.

**Open trades and pending orders:** entry, current price, floating P/L, stop,
target, time open against the maximum holding time, the latest agent review and
its time, and the time left before a pending order expires.

**Trade history:** broker ticket, instrument, direction, entry, exit, volume,
pips, net result, initial stop, net R, status, exit reason, opened and closed
times (UTC), variant and proposal source, and a link to the full journal of the
decisions behind the trade.

Rules for this page:

- Metrics are computed on the server from the journal and broker-reconciled
  fills (shadow records for shadow mode). The frontend only displays them.
- Net figures include the broker's commission and swap. A missing fee is shown
  as unknown, not as zero.
- Each metric shows its definition, for example that average win / average loss
  is a realized payoff ratio and not R.
- A metric without enough data says so instead of showing a misleading number,
  for example an annualized CAGR from a few weeks of trading.
- Research scoring uses the same metric implementation, so a number means the
  same thing on both sides.

### 9.9 Ownership from the start

New tables for settings, journal, positions and research runs carry their owner
(user and account) from the first version, with one initial admin as owner in
the single-user deployment. Adding users later then adds sign-in and access
checks without changing the meaning of existing records.

## 10. Current state and build order

| Component | State |
| --- | --- |
| Live capture: cBot → HTTPS ingress → API → PostgreSQL | Running ([CAPTURE.md](operations/CAPTURE.md)) |
| Historical tick exporter cBot | Implemented ([TICK_EXPORT.md](data/TICK_EXPORT.md)) |
| OpenAI adapter, model profiles and budget | Implemented |
| Shadow Executor: one GPT agent, quotes only, `NO_SIGNAL`/`WAIT`/`LONG`/`SHORT`, manual schedule, no positions | Implemented ([SHADOW_EXECUTOR.md](operations/SHADOW_EXECUTOR.md)) |
| Replay tick archive (Parquet, built from verified exports) and point-in-time market context | Implemented |
| Replay of news and macro context, decision schedule, Scout, GPT/Claude analysts, Jev validation, watchlist | Target |
| Shadow positions and position review (`HOLD`/`CLOSE`/`ADJUST`) | Target |
| Claude and Jev adapters | Target |
| User settings, Risk Engine, execution cBot, demo/live execution | Target |
| News and macro capture: GDELT GKG, Fed, ECB and BoE feeds, FRED/ALFRED | Running ([NEWS.md](operations/NEWS.md)) |
| Policy-meeting calendar and release times, scoring, research runs | Target |
| Users and roles, built-in sign-in and request limits, global signals over WebSocket, credential store, console | Target |

Build order, each step a working vertical slice:

1. **Post-cutoff data:** export ticks for EURUSD, GBPUSD and XAUUSD with the
   batch tool; news and FRED macro capture are running and GDELT is being
   back-filled; add policy-meeting dates and release times.
2. **Replay engine:** point-in-time context at `T` from archive and capture data.
3. **GPT analyst** through replay with **shadow positions and position review**
   (`HOLD`/`CLOSE`/`ADJUST`), scoring and baselines including a static exit;
   then the **Claude adapter and analyst**.
4. **Jev adapter, validation and final decision.**
5. **User settings and Risk Engine** in the replay and shadow path,
   including forced closes.
6. **Scout, the `WAIT` watchlist and pending orders with expiry.**
7. **Research runs**, single and continuous, over the journal.
8. **Scheduled shadow** on live data, then **demo** execution with the execution
   cBot, its local limit enforcement and the failover tests in Section 7.7.
9. **Platform and console:** users and roles, built-in sign-in and request limits
   for the control API, per-user credentials, global signals over WebSocket,
   and the mobile-first, WCAG 2.2 AA console with the controls in Section 3, the
   performance and history page, the journal and pipeline state.

## 11. Code layout

```text
src/ledgerquant/
  capture/        live capture API, contracts and storage (implemented)
  decision/       shadow Executor contract, runner and store (implemented)
  integrations/   model provider adapters (OpenAI implemented)
  models/         model profiles, generation types, budget (implemented)
  news/           news and macro capture: GDELT, central-bank feeds, FRED/ALFRED (implemented)
  replay/         tick archive and point-in-time market context (started)
  records.py      canonical JSON and content hashes
cbots/            cTrader cBots: LiveCapture, TickExport, MarketData probe
deploy/           Docker Compose for capture, news and manual shadow runs
tools/            operator tools, such as the batch tick export
migrations/       Alembic schema history
```

New packages (`pipeline/`, `risk/`, `execution/`, `journal/`,
`research/`) are added when their first slice is built, not before.
