# Replay data

**Status (11 October 2026):** The replay archive, the point-in-time context and
the decision plan are implemented. No agent has been run through replay yet.

Replay reads pinned files under the ignored `data/archive/`, never the live
database, so a replay can be repeated on exactly the same inputs. Each part has a
manifest with its sources and row counts.

## Build the inputs

```bash
# Ticks: rebuilt per symbol from verified TickExport runs (hash, size and row checks)
PYTHONPATH=src .venv/bin/python -m ledgerquant.replay.archive \
  --symbol EURUSD --symbol GBPUSD --symbol XAUUSD

# News, macro vintages and the release calendar, read from the capture database
PYTHONPATH=src .venv/bin/python -m ledgerquant.replay.snapshot
```

Rebuild the tick archive after new exports, and take a new snapshot after the
GDELT backfill has advanced. Both replace the previous version only after they
succeed. A replay records which archive and snapshot manifests it used.

## Context at a decision time

`ledgerquant.replay.context.replay_context(symbol, T, ticks, news)` returns what
was visible at `T` for one instrument:

| Part | Content |
| --- | --- |
| `market` | Latest quote with age and status, M5/H1/D1 bars with spreads; the forming bar is cut at `T` and marked incomplete |
| `news` | Up to 25 recent GDELT headlines matching the instrument (`news_recipe_v1`) and up to 10 central-bank releases from the last 7 days |
| `macro` | The last three observations of each tracked FRED series, from the latest vintage visible at `T` |
| `calendar` | Scheduled US CPI, employment, GDP, PCE, retail sales, claims and euro-area HICP releases from 3 days back to 7 days ahead |
| `sentiment` | `UNAVAILABLE` before 9 October 2026 |
| `assumptions` | The visibility rules this context relies on |

Visibility rules (architecture, Section 5.2): exported ticks are visible at
their event time; backfilled GDELT items 15 minutes after their batch time;
macro vintages from the UTC day after their `realtime_start`. The calendar is
the schedule as captured, so a reschedule announced after `T` may show. A
replay over backfilled data is a retrospective simulation, not live
performance.

## Decision plan

`ledgerquant.replay.schedule.plan(start, end, profiles)` lists the hourly
decision times (07:00–20:00 UTC, Monday–Friday) and labels each one
`DEVELOPMENT`, `HOLDOUT`, `AFTER_HOLDOUT` or `CONTAMINATED` from the latest
`training_data_cutoff` among the model profiles. It refuses a profile without a
cutoff, refuses holdout times unless `allow_holdout` is passed, and refuses
contaminated times unless `allow_contaminated` is passed for pipeline debugging.

## Measured performance

On this machine a full context takes about 0.25 s. The tick archive holds
114.4 million ticks in 779 MB; the news snapshot of 1.38 million items (GDELT
backfill through mid-December 2025) takes about 15 s to build.

## Broker terms for costs

Replay nets every trade of commission and estimated swap using
`configs/broker_terms/icmarkets-eu-real.json`: the broker's symbol terms and the
swap markup calibrated from them. Refresh the terms with the order-free
`cbots/LedgerQuant.SymbolTerms` probe, which prints the symbol's commission,
swap and size terms once in a cTrader CLI backtest and stops. Build it with
`dotnet build -c Release`, run it with the same `docker run ... backtest` command
as the tick exporter (any past one-day window, one `--symbol` per run), and take
the `SYMBOL_TERMS` line from the log. Store raw output under the ignored
`data/broker_terms/`; the config keeps only symbol terms, never account balances
or identifiers. Recalibrate the markup when the terms change.

## User limits in a run

Positions have no fixed holding limit. They end at the stop, at the target, when
the agent closes them, or at a user limit. Closing before the weekend is a
user-chosen risk limit (on by default, `--no-weekend-close` to turn it off). The
agent gets `limits.close_before_weekend` and `market_times.hours_to_weekend_close`
in its context. A deterministic check (`replay/risk.py`, a precursor to the Risk
Engine) rejects an entry when its `expected_horizon_hours` is longer than the
time to the weekly close. It never shortens the horizon or moves a level. The
rejected decision is journalled as `RISK_REJECTED` with `risk_reason`. The agent
is then asked once more for the same time, with `risk_feedback` in its context;
if that proposal is also rejected, no position is opened. Run directories are
named `<UTC start>_<contract>_<model>_<plan start date>`.

## Running the Claude analyst

The provider follows the model profile. `configs/models/anthropic_opus46.profile.json`
selects Claude Opus 4.6 (same August 2025 training cutoff as GPT-5.4 mini) through
the official `anthropic` SDK with retries off. Adaptive thinking cannot be combined
with a forced tool call, so the request asks for exactly one tool call with
`tool_choice: auto`; an answer without it is journalled as `NO_TOOL_CALL`. Put the
API key in `credentials/anthropic-api.key` (mode 600), then run, for example:

```bash
PYTHONPATH=src .venv/bin/python -m ledgerquant.replay.run --profile configs/models/anthropic_opus46.profile.json \
  --start 2025-09-08 --end 2025-09-13 --cost-cap 40
```

At the token use measured with GPT (about 12 400 input and 1 200 output tokens
per decision, 210 decisions per week), a week costs roughly 25-35 USD with Opus
4.6; measure it with a smoke run first.

Every report (`python -m ledgerquant.replay.report <run dir>`) compares the agent
with always long, always short and 23-hour momentum at the same decision times,
using the agent's own geometry and the same costs (`replay/baselines.py`).
