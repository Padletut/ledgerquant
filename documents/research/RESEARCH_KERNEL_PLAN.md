# Research data readiness and Research Kernel plan

**Date:** 09 October 2026

**Status:** A bounded exporter has produced live-account EURUSD ticks for 1–2 January 2020 and GBPUSD ticks for 2 January. The EURUSD rows match a separate cTrader Desktop export exactly. A scan of that Desktop file found EURUSD observations on 313 UTC dates in 2020. Intraday coverage, GBPUSD breadth and broker quote/cost semantics remain open; no certified historical tick archive or Research Kernel exists yet.

This plan starts with broker-data evidence. The initial measurement scope is IC Markets EU live account ACCOUNT_REDACTED, EURUSD and GBPUSD, from 2020 onward. Other accounts, symbols and asset classes enter only after separate source and schedule checks. The target architecture and authority boundaries remain in [ARCHITECTURE.md](../ARCHITECTURE.md); measured source limits remain in [DATA_AVAILABILITY.md](../data/DATA_AVAILABILITY.md).

## 1. Establish a usable broker-price dataset

1. **Record the source contract.** Identify broker entity, account environment, server where obtainable, exact broker symbol, cTrader/CLI version, tick-data mode, quote units and timestamp semantics. Record the extraction run and `.algo` hash. Keep broker ticks separate from Dukascopy and other external prices; a source substitution is a new dataset and evaluation assumption.
2. **Extract in bounded, resumable intervals.** Start with EURUSD and GBPUSD in the live account. Use contiguous calendar slices from 2020 rather than one unbounded backtest or a large `LoadMoreHistory()` collection. Use an overlap/warm-up interval and verify interior rows: a January backtest begun on 1 January missed its first observed tick, while a 31 December warm-up recovered all 1,545 rows and matched the Desktop export. Preserve every physical bid/ask update, including distinct updates with the same timestamp. Write immutable chunks and a manifest with exact observed time bounds, row count, source identity, schema version and content hash. The [bounded exporter](../data/TICK_EXPORT.md) has produced 1–2 January EURUSD and 2 January GBPUSD; a full-January row-level extraction and broader boundary checks remain before a full backfill.
3. **Measure quote fidelity and coverage from the extracted rows.** Produce UTC daily and intraday counts, first/last tick, nonpositive or crossed quotes, reversed timestamps, equal timestamps, spread distribution, suspicious pauses and boundary overlaps. The EURUSD Desktop CSV matches 32,201 CLI rows exactly across 1–2 January, validating the extraction path for those dates, but many equal bid/ask rows remain. Its [2020 daily report](../data/measurements/icm-eu-live-eurusd-desktop-2020-daily-coverage.json) shows 17,504,350 rows on 313 UTC dates, yet pauses within observed days require schedule and source checks. Establish broker quote/cost semantics from a separate broker-native interface, export or documented contract before setting cost-sensitive quality thresholds or launching a multi-month CLI sweep. Exclude the Desktop file's 2018–2019 four-record-per-hour prefix from tick-level coverage; its earliest row is not evidence of a 2018 tick archive. A CLI date argument is not a coverage boundary; observed first and last ticks are. Compare overlapping extraction slices to detect inconsistent downloads. Broker minute bars may be used as a diagnostic cross-check, never as fabricated replacement ticks.
4. **Resolve the market calendar.** Keep the ordinary weekly schedule, dated broker holiday/early-close notices and observed quote pauses as separate evidence. cTrader's current `MarketHours.Sessions` and `Holidays` are useful to inspect, but cannot alone prove the schedule years ago. Mark intervals `CONFIRMED_CLOSED`, `OPEN_WITH_OBSERVATIONS`, `OPEN_NO_OBSERVATIONS`, or `SCHEDULE_UNVERIFIED`, with a source reference and exact UTC bounds. Christmas and 1 January require year-, symbol- and broker-specific checks; 1 January 2020 had late ticks in both tested pairs. Do not turn every low-liquidity interval into a data defect, or excuse an open-session gap by naming a holiday.
5. **Choose the eligible start only after the audit.** Register source-quality thresholds before the complete sweep. Report each month and each unresolved open-session interval for the required pair set. Use 2020 only for the periods that satisfy the declared gate. If 2020 cannot support the intended contract, choose the earliest later *common* start for the required symbols and retain the failed intervals and reasons. A later start is a dataset decision, not a repair of failed research validation.

The output of this stage is a versioned, immutable broker-price snapshot plus a coverage report and explicit unresolved-interval list. A 2020 tick sample, `GetServerFirstTime()` or a backtest that completes cannot by itself satisfy this stage.

## 2. Define the research dataset boundary

Create a dataset view that names exact chunk hashes, account/feed, symbols, UTC interval, canonicalizer version and coverage report. Freeze development and validation windows before results are inspected. Read only declared intervals and retain equal-timestamp updates in stable source order. A dataset view must fail if a required chunk or checksum is missing; derived bars and features retain their source references and can be rebuilt.

Historical tick backfill has old **event time** but a later **retrieval/ingest time**. A study that reconstructs what a price-based rule might have seen in 2020 must be labelled `retrospective historical simulation`, with its assumptions stated. It is not a recorded-output replay and does not establish historical availability of news, cTrader sentiment or later-derived features. The first reliable cTrader sentiment collection began in October 2026; it cannot be used as a 2020 decision input. GDELT's indexed 2020 news gaps and article-level timing uncertainty also prevent declaring a general 2020 news-ready dataset.

## 3. Build the smallest complete Research Kernel slice

After one broker-price snapshot passes its source-quality gate, implement one end-to-end offline research path with a **preregistered, bounded** hypothesis. The vertical slice should contain:

- an immutable hypothesis contract covering decision, feature, payoff, cost, symbols, development/validation windows, minimum support, success/failure gates and trial budget;
- deterministic, point-in-time bounded dataset access and a candidate calculation over the frozen development window;
- an independent evaluator that alone reads frozen validation outcomes and writes typed measurements, uncertainty, costs, tails, breadth and failure reasons;
- an append-only trial and evidence record, including rejected/null outcomes and exact dataset/code/contract hashes;
- a read-only report that distinguishes development, historical validation and any later prospective evidence.

The initial slice should use a deterministic candidate to verify data access, cost accounting, validation isolation and evidence lineage before connecting Critic, Research or Discovery agents. Loop A then varies one registered component under a fixed payoff contract. Loop B introduces a new frozen payoff contract before independent validation. Neither an agent nor an optimizer may redefine success after observing holdout results. Shadow, demo and live promotion remain separate later workflows.

## 4. Order and completion gates

| Order | Deliverable | Gate to continue |
| --- | --- | --- |
| 1 | Bounded broker-tick exporter and source manifest for one short interval | **Acquisition and Desktop consistency verified** for EURUSD 1–2 January 2020: all 32,201 timestamps and bid/ask pairs match, the warm-up recovers the first New Year's tick, hashes agree and no trades occurred. **Source-quality gate open:** a separate broker quote/cost contract or interface must support economically valid cost assumptions; GBPUSD and later periods have not had a Desktop row comparison. |
| 2 | 2020-onward coverage audit for EURUSD and GBPUSD | EURUSD Desktop daily presence is measured for 2020; intraday pauses, historical broker schedule and GBPUSD remain open. Begin the multi-month CLI sweep only after the quote-source question is resolved. Record unresolved open-session intervals explicitly; freeze start date and quality thresholds before research outcomes. |
| 3 | Immutable dataset snapshot and bounded query path | Missing/corrupt chunks fail closed; source and backfill timing survive every derived view. |
| 4 | One frozen hypothesis and independent evaluation slice | Development cannot read unreleased validation results; all trials and failures remain visible. |
| 5 | Agent-driven proposal and optimization | Only registered search spaces and development evidence are visible; evaluator and promotion authority stay independent. |

Useful ideas from `/mnt/sda3/fx-algo` are bounded tick-window reads, preserving equal-time updates, source hashes and fail-closed dataset certification. Its Dukascopy files and normal FX execution calendar are **not** IC Markets coverage or historical holiday evidence. Any reused logic needs a LedgerQuant source contract and focused tests.
