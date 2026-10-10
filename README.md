# LedgerQuant

LedgerQuant is a multi-agent CFD trading system. GPT and Claude analyze the
market and propose trades, Jev validates them and makes the final decision, and
an independent, deterministic Risk Engine protects capital. It is not a
rule-driven system: fixed price rules exist only as baselines to compare the
agents against.

| Question | Answer |
| --- | --- |
| Who analyzes the market? | GPT and Claude, independently. They do not need to agree. |
| Who finds setups? | The agents themselves. |
| Who decides `LONG`, `SHORT`, `WAIT` or `NO_SIGNAL`? | GPT and Claude propose; Jev validates and decides. |
| Who protects capital? | The Risk Engine: deterministic code with limits set by the user. |
| What does Research do? | A run, started by the user, that makes the agents better traders. |

> **Status:** early development. LedgerQuant does not place orders yet. What
> runs today is data collection and a manual, non-trading shadow agent. See
> [Current state](#current-state).

## How it works

A clock starts a decision cycle for a point in time `T`. The same pipeline runs
live and in historical replay; only the data source differs.

```text
Context at T ─► Scout ─► GPT analyst ┐
                         Claude analyst ┴─► Jev: validate and decide ─► Risk Engine ─► Execution ─► Journal
```

- **Context** contains only data that was actually available at `T`. Missing
  sources are marked as missing, never guessed.
- **Scout** shortlists instruments; most are dropped.
- **GPT and Claude** each analyze news, sentiment and charts and propose
  `NO_SIGNAL`, `WAIT` or `LONG`/`SHORT` with a setup (thesis, stop, target).
- **Jev** runs risk checks and scenario analysis and chooses among the proposals.
  It never invents its own levels.
- **Risk Engine** sizes the position from the agent's stop and approves or
  rejects it under the user's limits. It never changes the agents' stop or target.
- **Execution** goes from shadow (no orders) to demo to live. A broker-side cBot
  keeps stops and limits in force even when LedgerQuant is down.
- **Journal** records every input, output, cost and outcome.

Agents also manage open positions (`HOLD`, `CLOSE`, `ADJUST`). Research compares
pipeline variants on the same decision points after the models' training
cutoffs, so results are not explained by what a model already knows.

The full design, including failover, multi-user operation and global signals,
is in [documents/ARCHITECTURE.md](documents/ARCHITECTURE.md).

## Current state

| Component | State |
| --- | --- |
| Live broker capture: cTrader cBot → HTTPS ingress → API → PostgreSQL (ticks and cTrader sentiment, ~100 symbols) | Running |
| News capture: GDELT GKG (FX and gold scope), Fed, ECB and BoE press feeds | Running |
| Macro capture: FRED release calendar and ALFRED vintages for 14 series | Running |
| Historical tick export via cTrader CLI, with a resumable batch tool | Implemented |
| OpenAI model adapter, model profiles and budget | Implemented |
| Shadow Executor: one GPT agent, quotes only, manual schedule, no orders | Implemented |
| Replay engine, Scout, GPT/Claude analysts, Jev, Risk Engine, execution, console | Planned |

The build order is in [Section 10 of the architecture](documents/ARCHITECTURE.md#10-current-state-and-build-order).

## Repository layout

```text
src/ledgerquant/
  capture/        live capture API, contracts and storage
  decision/       shadow Executor contract, runner and store
  integrations/   model provider adapters (OpenAI)
  models/         model profiles, generation types, budget
  news/           news and macro capture: GDELT, central-bank feeds, FRED/ALFRED
  records.py      canonical JSON and content hashes
cbots/            cTrader cBots: LiveCapture, TickExport, MarketData probe
configs/models/   model profiles
deploy/           Docker Compose, Dockerfile, Caddy ingress, secret initializer
migrations/       Alembic schema history
tools/            operator tools, such as the batch tick export
tests/            unit, contract and integration tests (Python and .NET)
documents/        architecture, data availability and operations guides
```

## Getting started

Requirements: Docker with Compose, Python 3.12, and for broker data a cTrader
account with cTrader Desktop (live capture) or the official cTrader CLI image
(historical export).

### Run the tests

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

### Start the data stack

```bash
python deploy/init_secrets.py
docker compose -f deploy/compose.yaml up --build -d
docker compose -f deploy/compose.yaml ps
```

This starts PostgreSQL, applies the migrations, and runs the capture API, the
HTTPS ingress and the news service. `init_secrets.py` creates the local secrets
under the ignored `credentials/` directory and never overwrites existing ones.
It creates an empty `credentials/fred-api.key`; put a
[FRED API key](https://fred.stlouisfed.org/docs/api/api_key.html) in it to enable
macro capture.

pgAdmin runs at <http://127.0.0.1:5050>, reachable from this machine only
(`LEDGERQUANT_PGADMIN_BIND` changes the address). Sign in with
`admin@ledgerquant.dev` (or `LEDGERQUANT_PGADMIN_EMAIL`) and the password in
`credentials/pgadmin.pwd`. The `LedgerQuant` server is preconfigured; it asks for
the database password from `credentials/postgres.pwd`. It connects as the owner
role; capture, news and decision tables reject updates and deletes.

Next steps:

- **Live broker capture:** install the LiveCapture cBot in cTrader Desktop and
  trust the ingress certificate. See [CAPTURE.md](documents/operations/CAPTURE.md).
- **News and macro:** follow the service and run the GDELT backfill. See
  [NEWS.md](documents/operations/NEWS.md).
- **Historical ticks:** put `CTRADER_ID` and `CTRADER_ACCOUNT_NUMBER` in the
  ignored `.env` and the cTrader password in `credentials/ctrader-cli.pwd`, then
  run, for example:

  ```bash
  .venv/bin/python tools/tick_export_batch.py --symbol EURUSD \
    --start 2025-09-01 --end 2026-10-09 --out data/ctrader_tick_exports/post_cutoff_v1/EURUSD
  ```

  See [TICK_EXPORT.md](documents/data/TICK_EXPORT.md).
- **Shadow Executor:** a manual, non-trading GPT decision on live quotes. See
  [SHADOW_EXECUTOR.md](documents/operations/SHADOW_EXECUTOR.md).

## Data and time

Every record keeps the time it was observed and the time LedgerQuant obtained it.
Live data has a real `available_at`; backfilled data has none, because a
download today does not show when it could first have been read. What exists,
how far back it goes, and what is still unverified (for example historical
spread quality) is measured in
[DATA_AVAILABILITY.md](documents/data/DATA_AVAILABILITY.md).

## Documentation

| Document | Contents |
| --- | --- |
| [ARCHITECTURE.md](documents/ARCHITECTURE.md) | Target design, decision pipeline, failover, platform, build order |
| [AGENTS.md](AGENTS.md) | Working rules for coding agents and contributors |
| [DATA_AVAILABILITY.md](documents/data/DATA_AVAILABILITY.md) | Measured coverage of ticks, sentiment, news and macro data |
| [CAPTURE.md](documents/operations/CAPTURE.md) | Live broker capture setup and operation |
| [NEWS.md](documents/operations/NEWS.md) | News and macro capture, time fields and limits |
| [TICK_EXPORT.md](documents/data/TICK_EXPORT.md) | Historical tick export from cTrader |
| [SHADOW_EXECUTOR.md](documents/operations/SHADOW_EXECUTOR.md) | Manual shadow decisions |

An earlier research-governance track was retired. Its code and documents are
preserved under the git tag `archive/research-governance-v1`.

## Safety

- LedgerQuant does not place orders yet. The market-data cBots expose no trading
  operations.
- Agents will only ever propose. Orders go through the Risk Engine and a
  broker-side execution cBot, under limits only the user sets.
- Credentials live in ignored files (`.env`, `credentials/`) and never enter
  model input, logs or the journal.

## License

[MIT](LICENSE)
