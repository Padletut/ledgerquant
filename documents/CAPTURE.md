# Live cTrader capture bootstrap

**Status:** PostgreSQL, Alembic and ingest API verified locally on 8 October 2026. The live-capture cBot builds, but has not been started in cTrader Desktop. No live sentiment collection is confirmed yet.

This is the first data-preservation path for current `Symbol.Sentiment` observations and, optionally, live broker bid/ask ticks. It does not place orders. cTrader sentiment is real-time only and cannot be backfilled through the Algo API. The existing `LedgerQuant.MarketData` cBot remains the separate read-only historical tick probe. [cTrader symbol sentiment](https://help.ctrader.com/ctrader-algo/guides/symbol-sentiment/)

## Start the local stack

From the repository root:

```bash
python deploy/init_secrets.py
docker compose -f deploy/compose.yaml up --build -d
docker compose -f deploy/compose.yaml ps -a
curl --fail http://127.0.0.1:18080/healthz
```

The initializer creates `credentials/postgres.pwd` and `credentials/collector-token.txt` with mode `0600` and never replaces existing values. Both files are ignored by Git and excluded from the Docker build context. The local `credentials/` directory should be accessible only to its owner. On hosts where the owner is not UID/GID 1000, set `LEDGERQUANT_SECRET_UID` and `LEDGERQUANT_SECRET_GID` to the secret-file owner's numeric IDs before running Compose. The database is private to the Compose network; the ingest API is published only to `127.0.0.1` on host port 18080 by default (`LEDGERQUANT_INGEST_PORT` can change it).

For a Portainer Git stack, provision the two secret files on the Docker host before deployment. Set `LEDGERQUANT_POSTGRES_PASSWORD_FILE` and `LEDGERQUANT_COLLECTOR_TOKEN_FILE` to their absolute host paths, plus the owning UID/GID variables. A Git checkout does not contain the ignored credentials. Keep the API behind a TLS ingress if cTrader runs on another machine; the default loopback URL works only when cTrader Desktop and the Compose host share that loopback network.

The migration job must exit with code 0 and `capture` must become healthy. `docker compose -f deploy/compose.yaml logs migrate capture` shows startup failures. Alembic owns the schema; do not recreate the database to apply a code update.

## Start collection in cTrader Desktop

Build the separate cBot:

```bash
dotnet build cbots/LedgerQuant.LiveCapture/LedgerQuant.LiveCapture/LedgerQuant.LiveCapture.csproj
```

Install its generated `.algo` in cTrader Desktop with the .NET 6 Algo runtime, attach one instance to each intended account and symbol, and set:

| Parameter | Required setting |
| --- | --- |
| `Feed ID` | Stable, unique ID for one broker, demo/live environment, account and symbol. Do not reuse it for another source. |
| `Ingest URL` | `http://127.0.0.1:18080/v1/capture/batches` only if Desktop runs on the same host. Otherwise use an HTTPS endpoint routed to the API. |
| `Collector token` | The exact value in `credentials/collector-token.txt`; treat the cTrader parameter/profile as secret material. |
| `Collect ticks` | Leave `false` for the first sentiment-only rollout. Enable only after measuring tick rate, disk write rate, PostgreSQL growth and journal lag. |
| `Maximum journal MiB` | Bound for the local append-only journal. A full journal stops the cBot visibly. |

`Symbol.Sentiment` does not work in cTrader CLI or Cloud. A CLI build or historical tick probe cannot start prospective sentiment collection. The Desktop instance must stay connected and running. On start, the cBot records a snapshot with `sentiment_trigger=startup`, then records `Updated` events. A startup snapshot is current state, not reconstructed history. Each instance writes an append-only NDJSON journal and acknowledgement cursor in its cTrader Algo local `capture/` storage; back up that directory along with PostgreSQL. [cTrader file operations](https://help.ctrader.com/ctrader-algo/guides/file-operations/)

The cBot logs `CAPTURE_STARTED`, `CAPTURE_TRANSPORT_RETRY`, `CAPTURE_REJECTED`, `CAPTURE_JOURNAL_FAILED` and `CAPTURE_STOPPED` with the remaining unacknowledged byte count. A retry keeps the original IDs. An authorization, validation or identity conflict stops the instance while retaining its journal. Fix the cause and restart with the same feed identity; do not delete or edit a pending journal to clear an error.

## Verify real observations

After starting Desktop, inspect the cBot log and check the database:

```bash
docker compose -f deploy/compose.yaml exec -T postgres \
  psql -U ledgerquant -d ledgerquant -c \
  "SELECT feed_id, environment, account_id, symbol, kind, count(*) AS observations, max(observed_at) AS latest_observed_at, max(received_at) AS latest_received_at FROM market.capture_observations GROUP BY feed_id, environment, account_id, symbol, kind ORDER BY feed_id, kind;"
```

An empty result means no broker observations have been ingested; container health alone does not prove collection. Compare cBot pending bytes, latest database times and the wall clock. The system does not yet have automatic feed-gap alerts or a coverage certificate. Record the exact first observed timestamp for every feed. Sentiment observed before that timestamp is unavailable from this collector.

## Data contract and durability

The wire protocol is version 1. A batch contains one feed identity, up to 250 observations and a `sent_at` timestamp. Each observation has a UUID message ID, feed/session/sequence identity, source and broker/account/symbol provenance, cBot version and `observed_at`. Ticks also have broker `event_at`, bid and ask. Sentiment carries buy/sell percentages and `startup` or `update`, with no invented broker event time. `received_at`, `ingested_at` and the bootstrap `available_at` are server timestamps. A zero percentage is stored with `ZERO_AMBIGUOUS` because the source may report zero when unavailable.

The API acknowledges only after a PostgreSQL commit. Repeated identical IDs are safe; changed payloads or a feed ID used for another source are rejected. PostgreSQL triggers reject updates, deletes and truncation of raw observations and feed bindings. The cBot local journal is flushed before send and its cursor moves after a valid acknowledgement. `available_at` is currently assigned inside the insert transaction and can precede its commit by the transaction duration. These raw rows must be canonicalized with a conservative post-commit availability bound before strict point-in-time replay or Executor use.

PostgreSQL rows are the bootstrap durable copy, including optional ticks. There is no Redis stream, archive chunk writer, automated retention, broker server ID, automatic clock-skew measurement, feed-gap detector, backup scheduler or historical cTrader sentiment backfill yet. The final market-data architecture will archive ticks outside PostgreSQL; do not treat this table as an unlimited five-year tick store.

## Backup and recovery

The Compose named volume survives ordinary container recreation, but it is not a backup. Schedule encrypted, access-controlled `pg_dump -Fc` backups of the `ledgerquant` database and retain the cTrader local `capture/` journal and cursor on the Desktop host. Verify restoration into a separate database periodically. Never restore an old PostgreSQL snapshot over a newer active capture database without reconciling the cBot journal and feed identities first. If the server is down, the cBot retries from its local journal until it reaches the configured size limit; a full or damaged journal stops capture and requires operator attention.

A manual database snapshot can be taken without stopping collection:

```bash
umask 077
mkdir -p "$HOME/ledgerquant-backups"
docker compose -f deploy/compose.yaml exec -T postgres \
  pg_dump -U ledgerquant -Fc ledgerquant \
  > "$HOME/ledgerquant-backups/ledgerquant-$(date -u +%Y%m%dT%H%M%SZ).dump"
```

Store a protected copy away from the Compose host and test restoring it into a separate database. This command does not back up the cTrader host's local journal.
