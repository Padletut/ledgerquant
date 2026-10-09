# Live cTrader capture bootstrap

**Status:** PostgreSQL, Alembic, ingest API and LAN HTTPS ingress verified on 9 October 2026. Live account ACCOUNT_REDACTED has committed sentiment from both the original EURUSD collector (`capture-0.1.2`) and the account-level, multi-symbol collector (`capture-0.2.0`). Multi-symbol ingestion is verified; long-running coverage remains unverified.

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

The `ingress` service publishes TLS only on `192.168.10.155:18443` by default (`LEDGERQUANT_INGEST_HTTPS_HOST` and `LEDGERQUANT_INGEST_HTTPS_PORT` configure the host binding). It forwards to the internal capture service. Caddy creates a local CA and stores its private key in the persistent `caddy_data` volume. The raw HTTP ingest port remains bound to host loopback. A cBot explicitly rejects a plain HTTP URL using a LAN address.

Export the **public** CA certificate after first startup:

```bash
docker compose -f deploy/compose.yaml exec -T ingress \
  cat /data/caddy/pki/authorities/local/root.crt \
  > credentials/ingress-ca.crt
curl --fail --cacert credentials/ingress-ca.crt \
  https://192.168.10.155:18443/healthz
sha256sum credentials/ingress-ca.crt
```

Copy `credentials/ingress-ca.crt` to the Windows cTrader VM. In PowerShell under the same Windows user that runs cTrader, import it into that user's trusted roots, then confirm the endpoint responds:

```powershell
Get-FileHash -Algorithm SHA256 C:\path\to\ingress-ca.crt
Import-Certificate -FilePath C:\path\to\ingress-ca.crt -CertStoreLocation Cert:\CurrentUser\Root
Invoke-RestMethod -Uri 'https://192.168.10.155:18443/healthz'
```

Compare the certificate file's SHA-256 hash from Linux and Windows through a trusted channel **before** importing it. Do not disable TLS certificate validation. If the `caddy_data` volume is lost, a new CA is generated and Windows must trust its new root before collection resumes.

For a Portainer Git stack, provision the two secret files on the Docker host before deployment. Set `LEDGERQUANT_POSTGRES_PASSWORD_FILE` and `LEDGERQUANT_COLLECTOR_TOKEN_FILE` to their absolute host paths, plus the owning UID/GID variables. A Git checkout does not contain the ignored credentials. The default HTTPS host binding assumes the Compose host owns `192.168.10.155`; change it if the deployment host has another address.

The migration job must exit with code 0 and `capture` must become healthy. `docker compose -f deploy/compose.yaml logs migrate capture` shows startup failures. Alembic owns the schema; do not recreate the database to apply a code update.

## Start collection in cTrader Desktop

Build the separate cBot:

```bash
dotnet build cbots/LedgerQuant.LiveCapture/LedgerQuant.LiveCapture/LedgerQuant.LiveCapture.csproj
```

Install its generated `.algo` in cTrader Desktop with the .NET 6 Algo runtime. Run one instance per intended account and choose its symbols in the parameters. The chart symbol and timeframe do not limit which configured symbols the cBot monitors. [cTrader multi-symbol parameters](https://help.ctrader.com/ctrader-algo/guides/parameter-types/), [cTrader symbol collection](https://help.ctrader.com/ctrader-algo/references/MarketData/Symbols/Symbols/)

| Parameter | Required setting |
| --- | --- |
| `Feed ID prefix` | Stable account-scoped prefix ending in `_`, for example `icm_live_ACCOUNT_REDACTED_`. The cBot derives one feed ID per symbol by appending the lowercase symbol name, escaping non-alphanumeric UTF-8 bytes as `_hh`. This preserves the existing `icm_live_ACCOUNT_REDACTED_eurusd` feed ID. Never reuse the prefix for another broker, environment or account. |
| `Symbols to capture` | Use cTrader's multi-symbol picker for an explicit set only when `Capture all enabled symbols=false`. Default selection is EURUSD. Duplicate or missing symbols stop startup. |
| `Capture all enabled symbols` | Default `true`: capture every symbol enabled on the account at startup. Restart to pick up changes to the enabled set. Review the resulting symbol count and storage load. |
| `Ingest URL` | On the Windows VM, use `https://192.168.10.155:18443/v1/capture/batches` after trusting the CA. The HTTP loopback URL works only if Desktop and Compose share a loopback network. |
| `Collector token` | The exact value in `credentials/collector-token.txt`; treat the cTrader parameter/profile as secret material. |
| `Collect ticks` | Leave `false` for the first sentiment-only rollout. Enable only after measuring tick rate, disk write rate, PostgreSQL growth and journal lag. |
| `Maximum journal MiB` | Per-symbol bound for local append-only journals. A full journal stops the account collector visibly. |

To replace the existing EURUSD-only instance, stop it and confirm its `CAPTURE_STOPPED` log reports `pending_bytes=0`. Keep a backup of its local `capture/` files, then install the new `.algo` on the same account. Set `Feed ID prefix` to `icm_live_ACCOUNT_REDACTED_` so EURUSD retains its original feed ID. Do not run the old and new instances for EURUSD at the same time. If pending bytes are nonzero, preserve that journal and its local storage location until its records are acknowledged; a replacement started in a different cTrader storage directory does not automatically recover them. Do not delete or rename an unacknowledged journal to make startup succeed.

The current bootstrap uses `[Robot]` because explicit Robot attribute settings caused the Windows cTrader 5.10.16 process to crash before `OnStart`. Its packaged time zone is UTC, but cTrader CLI reports `FullAccess` for this attribute. The code has no trading calls; `FullAccess` still grants broader host permissions than the intended restricted cBot. Run only the reviewed build on the dedicated capture VM, and recheck restricted attributes against cTrader Desktop before expanding deployment. This is an observed workaround, not a confirmed explanation of the platform crash.

`Symbol.Sentiment` does not work in cTrader CLI or Cloud. A CLI build or historical tick probe cannot start prospective sentiment collection. The Desktop instance must stay connected and running. For every configured symbol, the cBot records a snapshot with `sentiment_trigger=startup`, then records `Updated` events. A startup snapshot is current state, not reconstructed history. Each feed writes its own append-only NDJSON journal and acknowledgement cursor in cTrader Algo local `capture/` storage; back up that directory along with PostgreSQL. [cTrader file operations](https://help.ctrader.com/ctrader-algo/guides/file-operations/)

The cBot logs `CAPTURE_BOOT` as soon as `OnStart` runs, followed by `CAPTURE_STARTED` or a `CAPTURE_START_FAILED` reason. It also logs `CAPTURE_TRANSPORT_RETRY`, `CAPTURE_REJECTED`, `CAPTURE_JOURNAL_FAILED` and `CAPTURE_STOPPED` with the remaining unacknowledged byte count. A retry keeps the original IDs. An authorization, validation or identity conflict stops the instance while retaining its journal. Fix the cause and restart with the same feed identity; do not delete or edit a pending journal to clear an error. The Collector token is hidden from the cTrader instance title but remains sensitive in the parameter editor and saved parameter files.

If the instance stops, open that instance's **Log** tab in cTrader Algo and inspect the lines preceding the stop or automatic restart warning. Caddy writes the request method, path and HTTP status to the `ingress` container log, with request headers omitted. After another start attempt, run `docker compose -f deploy/compose.yaml logs --since=5m ingress` and look for `/v1/capture/batches`: `401` indicates a token mismatch, `422` an invalid batch, and `409` a feed or observation identity conflict. No access entry means no HTTP request completed; inspect the cBot log and its TLS connection before changing server data. A successful `/healthz` call from PowerShell tests Windows connectivity and certificate trust, but does not prove that the cBot started or sent a batch. Do not copy the Collector token into diagnostic reports. [cTrader cBot lifecycle](https://help.ctrader.com/ctrader-algo/how-tos/cbots/cbot-lifecycle/), [cTrader fault tolerance](https://help.ctrader.com/ctrader-algo/documentation/fault-tolerance/)

## Verify real observations

After starting Desktop, inspect the cBot log and check the database:

```bash
docker compose -f deploy/compose.yaml exec -T postgres \
  psql -U ledgerquant -d ledgerquant -c \
  "SELECT feed_id, environment, account_id, symbol, kind, count(*) AS observations, max(observed_at) AS latest_observed_at, max(received_at) AS latest_received_at FROM market.capture_observations GROUP BY feed_id, environment, account_id, symbol, kind ORDER BY feed_id, kind;"
```

An empty result means no broker observations have been ingested; container health alone does not prove collection. Compare cBot pending bytes, latest database times and the wall clock. The system does not yet have automatic feed-gap alerts or a coverage certificate. Record the exact first observed timestamp for every feed. Sentiment observed before that timestamp is unavailable from this collector.

**First confirmed live observation (9 October 2026, checked at 06:13 UTC):** Feed `icm_live_ACCOUNT_REDACTED_eurusd` on IC Markets EU Ltd live account ACCOUNT_REDACTED had one `sentiment` row. Its `observed_at` is `2026-10-09 06:11:50.104069+00`, `sentiment_trigger=startup`, `quality_flag=OBSERVED`, buy/sell percentages `63/37`, and `cbot_version=capture-0.1.2`. The HTTPS ingress returned HTTP 200 for the batch. PostgreSQL records `received_at=2026-10-09 06:11:51.524495+00` and `ingested_at=2026-10-09 06:11:51.534712+00`. At that check, only the startup snapshot had been verified. There were no tick rows; the initial setting leaves `Collect ticks` disabled.

**Subsequent verification (9 October 2026):** PostgreSQL contained two EURUSD startup snapshots and 20 `sentiment_trigger=update` rows from `capture-0.1.2`. The first update was observed at `2026-10-09 06:13:34.151696+00`; the latest at `2026-10-09 10:26:07.870568+00`. This confirms receipt of update events but does not establish gap-free coverage or that the Desktop instance is still running. No other symbol or tick feed was present at this check.

**Multi-symbol verification (9 October 2026, checked at 12:52:04 UTC):** PostgreSQL contained 177 `capture-0.2.0` sentiment observations across 101 distinct symbols on live account ACCOUNT_REDACTED: 101 startup snapshots and 76 update events. The first observed time was `2026-10-09 12:49:59.944735+00`. Examples beyond EURUSD include GBPUSD, AUDUSD, BTCUSD and XAUUSD. At this check, 45 symbols had at least one nonzero `OBSERVED` sentiment value; 101 rows were `ZERO_AMBIGUOUS`, mostly initial `0/0` snapshots. A stored zero is not a usable sentiment signal. No tick rows were present. This verifies committed multi-symbol data, not that every enabled symbol has valid sentiment or that collection will remain continuous.

## Data contract and durability

The wire protocol remains version 1. An account collector sends separate batches for each feed in round-robin order, with only one request in flight. A batch contains one feed identity, up to 250 observations and a `sent_at` timestamp. Each observation has a UUID message ID, feed/session/sequence identity, source and broker/account/symbol provenance, cBot version and `observed_at`. Ticks also have broker `event_at`, bid and ask. Sentiment carries buy/sell percentages and `startup` or `update`, with no invented broker event time. `received_at`, `ingested_at` and the bootstrap `available_at` are server timestamps. A zero percentage is stored with `ZERO_AMBIGUOUS` because the source may report zero when unavailable.

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
