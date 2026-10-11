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
