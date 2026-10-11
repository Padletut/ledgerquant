# Bounded cTrader historical tick export

**Status:** Experimental acquisition procedure, verified on bounded EURUSD, GBPUSD and XAUUSD windows on an IC Markets EU Ltd live research account. The output is not a certified research dataset or the durable market archive.

## Contract and limits

`cbots/LedgerQuant.TickExport/` contains a separate, observation-only cBot. It reads cTrader CLI server-tick backtests and writes one CSV plus a JSON manifest per run ID. It requires an actual tick before the requested interval and another tick at or after its exclusive end. The CSV includes every callback in source order, with an ordinal so equal-timestamp updates remain distinct. It rejects invalid or reversed quotes/times, an interval longer than seven days, more than the configured row limit, and an existing output artifact. It never calls the trading API and refuses non-backtest operation.

The manifest records account and broker identity, symbol, image digest, exact UTC event bounds, count, duplicate timestamps, equal bid/ask rows, CSV length and SHA-256, and extraction wall-clock times. `available_at_utc` and `observed_at_utc` remain null: a 2026 download does not prove historical point-in-time availability. `coverage_status` and `quote_quality_status` remain `UNVERIFIED`. A published manifest means this run reached its end witness and its CSV was hashed; it does not certify continuous coverage or quote fidelity. The CLI backtest API returned an empty `Account.BrokerName` in the tested Linux image. In that case, `broker_name_basis=cli_accounts_asserted` means the operator supplied the broker name from the authenticated CLI account listing; account number and live/demo mode came from the runtime API. Server identity remains unknown.

## Long intervals

`tools/tick_export_batch.py` runs the same procedure over a long interval, one
bounded backtest at a time. It splits the interval into chunks of at most seven
days, splits a chunk in half when it reaches the row limit, verifies every
manifest against its CSV, records every attempt in `batch.jsonl` and skips
verified runs when restarted. It reads `CTRADER_ID` and
`CTRADER_ACCOUNT_NUMBER` from the environment or the ignored `.env` and never
prints them. Run one symbol at a time:

```bash
.venv/bin/python tools/tick_export_batch.py --symbol XAUUSD \
  --start 2025-09-01 --end 2026-10-09 --chunk-days 4 --parallel 2 \
  --out data/ctrader_tick_exports/post_cutoff_v1/XAUUSD
```

The backtest replays every tick from its start, so most of a run's time can go to
the warm-up before the chunk. The tool therefore starts the backtest on the
previous weekday (Friday for a Monday chunk) and uses the full `--margin-days`
warm-up only when retrying a failed run, for example across a holiday. Larger
chunks need fewer warm-ups. XAUUSD had a median of about 170,000 ticks per
trading day in 2025–2026, so four-day chunks usually stay below the
1,000,000-row limit; volatile periods (up to about 340,000 per day in late
January 2026) exceed it and are split automatically. EURUSD and GBPUSD fit in
seven-day chunks. `--parallel` runs several backtests at once.

Each run needs an actual tick at or after its end as a witness. An end on a
weekend therefore completes only after the market has reopened, and an end at or
after the present cannot complete at all; the tool refuses an end within the
last hour. The cTrader CLI prints the login and account number; the tool
redacts both before storing a run's CLI log. Manifests still record the account
number in the ignored `data/` directory.

## One bounded run

1. Build the nested project and record the `.algo` hash:

   ```bash
   dotnet build cbots/LedgerQuant.TickExport/LedgerQuant.TickExport/LedgerQuant.TickExport.csproj -c Release
   sha256sum cbots/LedgerQuant.TickExport/LedgerQuant.TickExport/bin/Release/net6.0/LedgerQuant.TickExport.algo
   ```

2. Verify the selected account in the authenticated cTrader CLI account listing. Use the pinned image below for comparable runs. Provide a cTrader ID through `CTRADER_ID` and the account number through `CTRADER_ACCOUNT_NUMBER`; keep the password in the existing ignored `credentials/ctrader-cli.pwd` file. Do not put the account number in tracked commands, reports or documentation. Create a new output directory for each batch and choose a unique run ID. This command illustrates the measured 2 January 2020 EURUSD interval; the CLI starts on 31 December to supply a warm-up tick and continues through 3 January to supply an end witness. The exporter itself accepts only `[2020-01-02T00:00:00Z, 2020-01-03T00:00:00Z)`.

   ```bash
   mkdir -p data/ctrader_tick_exports/2020-01-02
   docker run -d --name lq-tick-export-eurusd-20200102 \
     --mount type=bind,src="$PWD/cbots/LedgerQuant.TickExport/LedgerQuant.TickExport/bin/Release/net6.0",dst=/algo,readonly \
     --mount type=bind,src="$PWD/credentials/ctrader-cli.pwd",dst=/run/secrets/ctrader-cli.pwd,readonly \
     --mount type=bind,src="$PWD/data/ctrader_tick_exports/2020-01-02",dst=/export \
     ghcr.io/spotware/ctrader-console@sha256:285484fad431e0ffa4ca96662e82ea66cead93c97cf0e3c46006e80cab4734ba \
     backtest /algo/LedgerQuant.TickExport.algo \
     --ctid="$CTRADER_ID" --pwd-file=/run/secrets/ctrader-cli.pwd \
     --account="$CTRADER_ACCOUNT_NUMBER" --symbol=EURUSD --period=h1 \
     --start='31/12/2019 00:00' --end='03/01/2020 00:00' --data-mode=ticks \
     --StartUtc=2020-01-02T00:00:00Z --EndExclusiveUtc=2020-01-03T00:00:00Z \
     --OutputDirectory=/export --RunId=eurusd_20200102_next \
     --ExpectedAccountNumber="$CTRADER_ACCOUNT_NUMBER" --ExpectedBrokerName='IC Markets EU Ltd' \
     --CliImageDigest=sha256:285484fad431e0ffa4ca96662e82ea66cead93c97cf0e3c46006e80cab4734ba \
     --MaximumRows=250000 --full-access
   ```

   [cTrader CLI](https://help.ctrader.com/ctrader-cli/cbots/) documents the `backtest` and server `ticks` mode. The pinned 5.10.1.0 image above ran this .NET 6 package on the sampled EURUSD and XAUUSD windows; the older 5.6.8.0 image failed before cBot start on the tested XAUUSD CPI interval. A later CLI image needs separate verification. CLI options and cBot parameter names are distinct. Do not use a CSV data mode for this source contract.

3. Inspect `docker logs lq-tick-export-eurusd-20200102` for `TICK_EXPORT_COMPLETE` and zero trades in the CLI summary. If the exporter reports `TICK_EXPORT_FAILED` or `TICK_EXPORT_INCOMPLETE`, retain the log and partial artifact as failure evidence; do not treat the CSV as complete. The tested CLI image did not exit when the cBot stopped, so stop and remove this named container after collecting its result. Use a new run ID for a retry.
4. Check that the manifest's `row_count`, `data_bytes` and `data_sha256` match the CSV, and retain the exact `.algo` package and hash, CLI invocation/log and manifest together. Compare overlapping windows by exact interior rows; do not infer completeness from a successful exit or a count alone. The local `data/` directory is ignored by Git and is not a backup. Copy verified artifacts to managed storage before relying on them.

## Measured limitation

EURUSD exports with different warm-up starts were byte-for-byte identical. A run with CLI `--spread=1` and another with official CLI 5.10.1.0 also produced identical `Tick.Bid`/`Tick.Ask` rows in this one interval. cTrader Desktop CSV rows matched all 1,545 EURUSD rows on 1 January and all 30,656 on 2 January. Nevertheless, 28,912 of 30,656 EURUSD rows on 2 January and 14,238 of 80,762 GBPUSD rows had equal bid and ask. Those prices pass basic field validation and the EURUSD extraction comparison, but their economic spread quality is unresolved. Establish a separate broker quote/cost contract before using these quotes for cost-sensitive research. See [measured data availability](DATA_AVAILABILITY.md) and the [replay data requirements](../ARCHITECTURE.md#6-data).

## Desktop comparison gate

Retain the unmodified Desktop CSV and its SHA-256, plus the cTrader version, broker account, symbol, backtest data mode and requested interval. Inspect its columns, quote units, timestamp precision and time zone before parsing. Compare only the common declared UTC interval; report row counts, first/last events, exact timestamp-and-quote matches, unmatched rows and any transformations required for comparison. Do not round timestamps or prices until a documented precision difference has been identified, and keep the unrounded mismatch count. A match validates that the cBot exporter reproduces Desktop's downloaded backtest data; both may still depend on the same broker server history. Historical execution costs need a separately documented account commission/spread contract or broker-native quote check.

The [1–2 January EURUSD comparison](measurements/icm-eu-live-eurusd-desktop-comparison-2020-01-01_2020-01-02.json) had zero mismatches. A later [1 October gap cross-check](measurements/icm-eu-live-eurusd-2020-intraday-gap-crosscheck.json) also matched all 183 EURUSD rows in its bounded window, including the absence of rows within a 25-minute pause. These checks show cTrader export-path consistency, not historical broker quote fidelity or complete coverage. The Desktop file also contained a 2018–2019 prefix with exactly four fixed-time, equal bid/ask records per observed hour. Treat that prefix as unverified generated data, not earlier tick coverage, and filter it out of research snapshots.

The [XAUUSD quote-quality audit](measurements/xauusd-quote-quality-audit-v1.json) retains six bounded 2020 exports and six 2021 metadata-only probes. Its development evaluator checks manifest hashes and source identity, samples only previously observed quotes and reports all fixed anchors. The raw CSVs, manifests, full per-anchor result and CLI logs are local ignored artifacts; copy them to managed storage before treating the measurement as durable evidence. The 2021 quote outcomes were not opened.

The evaluator that produced this development result was retired with the research-governance track; it is preserved under the git tag `archive/research-governance-v1` together with the command that reproduces it.
