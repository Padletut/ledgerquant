# Bounded cTrader historical tick export

**Status:** Experimental acquisition procedure, verified on one UTC day for EURUSD and GBPUSD on IC Markets EU Ltd live account ACCOUNT_REDACTED. The output is not a certified research dataset or the durable market archive.

## Contract and limits

`cbots/LedgerQuant.TickExport/` contains a separate, observation-only cBot. It reads cTrader CLI server-tick backtests and writes one CSV plus a JSON manifest per run ID. It requires an actual tick before the requested interval and another tick at or after its exclusive end. The CSV includes every callback in source order, with an ordinal so equal-timestamp updates remain distinct. It rejects invalid or reversed quotes/times, an interval longer than seven days, more than the configured row limit, and an existing output artifact. It never calls the trading API and refuses non-backtest operation.

The manifest records account and broker identity, symbol, image digest, exact UTC event bounds, count, duplicate timestamps, equal bid/ask rows, CSV length and SHA-256, and extraction wall-clock times. `available_at_utc` and `observed_at_utc` remain null: a 2026 download does not prove historical point-in-time availability. `coverage_status` and `quote_quality_status` remain `UNVERIFIED`. A published manifest means this run reached its end witness and its CSV was hashed; it does not certify continuous coverage or quote fidelity. The CLI backtest API returned an empty `Account.BrokerName` in the tested Linux image. In that case, `broker_name_basis=cli_accounts_asserted` means the operator supplied the broker name from the authenticated CLI account listing; account number and live/demo mode came from the runtime API. Server identity remains unknown.

## One bounded run

1. Build the nested project and record the `.algo` hash:

   ```bash
   dotnet build cbots/LedgerQuant.TickExport/LedgerQuant.TickExport/LedgerQuant.TickExport.csproj -c Release
   sha256sum cbots/LedgerQuant.TickExport/LedgerQuant.TickExport/bin/Release/net6.0/LedgerQuant.TickExport.algo
   ```

2. Verify the selected account in the authenticated cTrader CLI account listing. Use the pinned image below for comparable runs. Provide a cTrader ID through `CTRADER_ID`; keep the password in the existing ignored `credentials/ctrader-cli.pwd` file. Create a new output directory for each batch and choose a unique run ID. This command illustrates the measured 2 January 2020 EURUSD interval; the CLI starts on 31 December to supply a warm-up tick and continues through 3 January to supply an end witness. The exporter itself accepts only `[2020-01-02T00:00:00Z, 2020-01-03T00:00:00Z)`.

   ```bash
   mkdir -p data/ctrader_tick_exports/2020-01-02
   docker run -d --name lq-tick-export-eurusd-20200102 \
     --mount type=bind,src="$PWD/cbots/LedgerQuant.TickExport/LedgerQuant.TickExport/bin/Release/net6.0",dst=/algo,readonly \
     --mount type=bind,src="$PWD/credentials/ctrader-cli.pwd",dst=/run/secrets/ctrader-cli.pwd,readonly \
     --mount type=bind,src="$PWD/data/ctrader_tick_exports/2020-01-02",dst=/export \
     ghcr.io/spotware/ctrader-console@sha256:a0f0c22d5bbe31db8de6e91b6caad9b8061b52d9133426aa6242848469c208e9 \
     backtest /algo/LedgerQuant.TickExport.algo \
     --ctid="$CTRADER_ID" --pwd-file=/run/secrets/ctrader-cli.pwd \
     --account=ACCOUNT_REDACTED --symbol=EURUSD --period=h1 \
     --start='31/12/2019 00:00' --end='03/01/2020 00:00' --data-mode=ticks \
     --StartUtc=2020-01-02T00:00:00Z --EndExclusiveUtc=2020-01-03T00:00:00Z \
     --OutputDirectory=/export --RunId=eurusd_20200102_next \
     --ExpectedAccountNumber=ACCOUNT_REDACTED --ExpectedBrokerName='IC Markets EU Ltd' \
     --CliImageDigest=sha256:a0f0c22d5bbe31db8de6e91b6caad9b8061b52d9133426aa6242848469c208e9 \
     --MaximumRows=250000 --full-access
   ```

   [cTrader CLI](https://help.ctrader.com/ctrader-cli/cbots/) documents the `backtest` and server `ticks` mode. The tested pinned image ran this .NET 6 package; a later CLI image may require a different target and separate verification. CLI options and cBot parameter names are distinct. Do not use a CSV data mode for this source contract.

3. Inspect `docker logs lq-tick-export-eurusd-20200102` for `TICK_EXPORT_COMPLETE` and zero trades in the CLI summary. If the exporter reports `TICK_EXPORT_FAILED` or `TICK_EXPORT_INCOMPLETE`, retain the log and partial artifact as failure evidence; do not treat the CSV as complete. The tested CLI image did not exit when the cBot stopped, so stop and remove this named container after collecting its result. Use a new run ID for a retry.
4. Check that the manifest's `row_count`, `data_bytes` and `data_sha256` match the CSV, and retain the exact `.algo` package and hash, CLI invocation/log and manifest together. Compare overlapping windows by exact interior rows; do not infer completeness from a successful exit or a count alone. The local `data/` directory is ignored by Git and is not a backup. Copy verified artifacts to managed storage before relying on them.

## Measured limitation

EURUSD exports with different warm-up starts were byte-for-byte identical. A run with CLI `--spread=1` also produced identical `Tick.Bid`/`Tick.Ask` rows in this one interval. Nevertheless, 28,912 of 30,656 EURUSD rows and 14,238 of 80,762 GBPUSD rows had equal bid and ask. Those prices pass basic field validation, but their economic spread quality is unresolved. Compare against an independent cTrader/IC Markets tick export or another documented broker-native path before using these quotes for cost-sensitive research. See [measured data availability](DATA_AVAILABILITY.md) and the [Research Kernel gates](../research/RESEARCH_KERNEL_PLAN.md).
