# Data availability: IC Markets ticks, news and sentiment

**Reviewed:** 08 October 2026

**Status:** Initial IC Markets tick probe completed for two symbols and two accounts. Full historical coverage and news-provider coverage remain unmeasured.

## Summary

| Dataset | Confirmed historical depth | What remains to be verified |
| --- | --- | --- |
| IC Markets ticks via cBot | **January 2020 confirmed in server-tick backtests** for EURUSD and GBPUSD on one IC Markets EU demo account and one live account. `GetServerFirstTime()` reported older dates, but direct `LoadMoreHistory()` was only tested with two bounded batches and did not reach 2020. | Measure monthly continuity, other symbols and asset classes, exact server identity, earliest retrievable tick through each access method, and bulk-export feasibility. |
| cTrader sentiment | **No history through the documented Algo API.** The data is available only in real time. | Whether a separate provider offers a licensed archive. A locally recorded history starts when collection begins. |
| Raw news and events | **Provider-dependent.** GDELT 2.0 metadata starts in 2015; Event Registry advertises a news archive since 2014. Neither claim verifies the specific 2020 corpus or full-text rights needed by LedgerQuant. | Original statement/article access, event coverage, first-seen times, revisions and usage rights. |
| Provider news sentiment | **Provider-dependent.** GDELT, Alpha Vantage, Event Registry and RavenPack expose different tone or sentiment fields. No provider-specific 2020 feed has been measured for LedgerQuant. | Historical field-level coverage, method/version, source linkage, calculation time and decision-time eligibility. |
| Macroeconomic series and vintages | **Series-dependent.** FRED has long historical series; ALFRED provides past data vintages. Observation history and revision history are different depths. | First release and revision coverage for each selected series, release timestamps, embargoes and point-in-time access. |

Three different questions matter: **what a source has stored**, **what our account and agreement allow us to retrieve**, and **when the information was actually available for a decision**. The presence of an old article or tick in an archive does not answer all three.

## 1. IC Markets: how far back can a cBot retrieve ticks?

cTrader Algo documents that `MarketData.GetTicks(symbolName)` returns a `Ticks` collection, `GetServerFirstTime()` returns the first available server tick time, and `LoadMoreHistory()` loads older ticks and returns the number added. An asynchronous loading method is also available. These methods allow direct measurement on the account, but the API documentation specifies no IC Markets retention period. [cTrader Algo: Ticks](https://help.ctrader.com/ctrader-algo/references/MarketData/Ticks/Ticks/)

On 9 June 2022, IC Markets Australia announced that historical data before 2020 would no longer be available on clients' trading accounts from 10 June 2022 and directed clients needing older data to support. This notice **does not establish** the earliest cTrader tick available today: it does not specify current coverage by cTrader server, instrument or account type. Treat it as a question for the relevant IC Markets entity, not as a fixed date in LedgerQuant. [IC Markets: historical data notice](https://www.icmarkets.com.au/blog/notice-regarding-client-historical-data/)

cTrader backtesting can use “tick data from server.” This establishes that server ticks can be used for backtesting, but does not say how far back a running cBot can retrieve them or how complete the series is. [cTrader: backtesting](https://help.ctrader.com/ctrader-algo/how-tos/cbots/backtest-a-cbot/)

### Initial account measurement: 8 October 2026

The read-only `TickHistoryProbe` lives in `cbots/LedgerQuant.MarketData/`. It was built with `cTrader.Automate` 1.0.21 and run in the official cTrader CLI Docker image, version 5.6.8.0 (`ghcr.io/spotware/ctrader-console@sha256:a0f0c22d5bbe31db8de6e91b6caad9b8061b52d9133426aa6242848469c208e9`). The image ran the built .NET 6 algo successfully. cTrader CLI used `backtest`, `--data-mode=ticks`, `--period=h1`, and UTC arguments `--start="06/01/2020 00:00" --end="07/01/2020 00:00"`. The actual observed ticks covered both 6 and 7 January, so the table uses observed timestamps rather than inferring an exclusive end from the CLI argument. No CSV or external tick source was supplied. [cTrader CLI: tick data mode](https://help.ctrader.com/ctrader-cli/cbots/)

| IC Markets EU account | Symbol | `GetServerFirstTime()` reported | First / last tick observed in backtest (UTC) | Ticks | Invalid bid/ask | Reversed timestamps |
| --- | --- | --- | --- | ---: | ---: | ---: |
| Demo, ending 4853 | EURUSD | 2014-01-19 | 2020-01-06 00:00:00.470 / 2020-01-07 23:59:53.628 | 66,796 | 0 | 0 |
| Live, ending 2334 | EURUSD | 2019-07-08 | 2020-01-06 00:00:00.470 / 2020-01-07 23:59:53.629 | 66,648 | 0 | 0 |
| Demo, ending 4853 | GBPUSD | 2014-01-19 | 2020-01-06 00:00:00.549 / 2020-01-07 23:59:41.589 | 145,019 | 0 | 0 |
| Live, ending 2334 | GBPUSD | 2019-07-08 | 2020-01-06 00:00:00.548 / 2020-01-07 23:59:41.589 | 145,057 | 0 | 0 |

The probe observed zero duplicate timestamps in these four short runs. The largest observed gap was under 248 seconds for EURUSD and under 131 seconds for GBPUSD; these are weekday-window measurements, not a coverage certificate. Demo and live tick counts differ, so they remain distinct datasets. The CLI account listing identified the broker entity and demo/live mode but did not expose a server name; the server identity is still an open provenance field. The cBot made no trading API calls and the CLI reported zero trades.

A separate direct `run` on the demo EURUSD account exercised `MarketData.GetTicks()`, `GetServerFirstTime()` and two calls to `LoadMoreHistory()`. They added 34,241 ticks in total; the earliest loaded tick was 2026-10-07 22:52:25.629 UTC. The probe stopped at its configured two-batch limit with `RESOURCE_LIMIT`. This confirms that direct history loading works, but **does not establish that a running cBot can page directly back to 2020 within acceptable time or memory**. The reported 2014/2019 server-first dates are not a substitute for retrieved ticks at those dates. [cTrader Algo: Ticks](https://help.ctrader.com/ctrader-algo/references/MarketData/Ticks/Ticks/)

**Current finding:** the tested IC Markets EU demo and live accounts can supply server ticks for EURUSD and GBPUSD in the sampled January 2020 window through cTrader CLI backtesting. The result supports a 2020 research start for those tested windows; it does not prove complete 2020–2026 coverage, direct cBot bulk retrieval, or availability on other accounts or symbols. These runs measured ticks but did not export a research-ready raw tick archive.

### Measure coverage on the actual account

Run a small, **read-only** probe in the intended cTrader Desktop/.NET environment, first on demo and then on the relevant live account if they use different servers. Include every symbol intended for research or trading, with at least one active FX pair and each other relevant asset class. Record the following for each combination:

| Field | Purpose |
| --- | --- |
| IC Markets entity, demo/live, server, account alias and cTrader version | Access and history may differ; do not store login secrets in the report. |
| Exact broker symbol, symbol ID where available, and test time in UTC | Symbol names and server history may change. |
| `GetServerFirstTime()` and the time of the earliest **successfully retrieved** tick | Detects differences between the reported boundary and retrievable data. |
| First and last tick and tick count for selected windows | Shows whether the start date represents usable coverage. |
| Bid/ask availability, timestamps, duplicates, gaps and weekend boundaries | Determines whether the data supports cost and execution analysis. |
| Runtime, errors, and any throttling or memory limits | Determines whether retrieval is operationally feasible. |

Read `GetServerFirstTime()` first. Then verify a short window around that date and several later windows. Do not load years of ticks into one long-lived cBot collection without a resource limit. If using `LoadMoreHistory()`, load backward in controlled steps, record the returned count and check that the earliest actual tick moves backward. Interpret zero results or errors alongside connection state, server status and the symbol's trading schedule; one zero result alone does not prove a global retention limit.

For an independent check, cTrader Open API can retrieve historical ticks in requests spanning **at most one week**. This is a limit **per request**, not a claim that only one week of data is retained. A response may be truncated at a backend-dependent tick limit; handle `hasMore` before declaring a window complete. Keep Open API results distinct from cBot results in the measurement report. [cTrader Open API: symbol data](https://help.ctrader.com/open-api/symbol-data/)

cTrader Algo 5.10 also documents CSV export of data downloaded for backtesting or optimization, and import of custom tick CSV data. This may offer a useful cross-check or alternative research route **if the installed client version and account support it**. Neither export capability nor a selectable backtest period proves how much IC Markets data is available. [cTrader Algo: 5.10 changelog](https://help.ctrader.com/ctrader-algo/documentation/changelog/)

**Questions for IC Markets:** What is the earliest available bid/ask tick for each relevant symbol on our cTrader server, separately for demo and live? Is coverage the same through cBot/Algo, backtesting and Open API? Does the 2022 notice still apply to this entity and server? Can support provide older data, and if so, in what format, with which timestamps and usage rights?

## 2. News and sentiment

### cTrader sentiment

`Symbol.Sentiment` exposes buy/sell percentages and update events. cTrader explicitly states that this data is available only in real time, with no stored history for backtesting or optimization. The API objects are documented for .NET 6 algorithms and do not work in cTrader Cloud or CLI. Check this against the intended deployment mode before designing a cBot-based sentiment collector. [cTrader Algo: symbol sentiment](https://help.ctrader.com/ctrader-algo/guides/symbol-sentiment/)

cTrader describes the figures as percentages of accounts expecting a rise or fall, aggregated across available cTrader servers. They are therefore not a measure of IC Markets positioning alone. The API reference also says a percentage can be `0` when data is unavailable; do not automatically treat `0` as a genuine market signal. [cTrader: market sentiment](https://help.ctrader.com/ctrader/charts/market-sentiment/), [cTrader Algo: `SymbolSentiment`](https://help.ctrader.com/ctrader-algo/references/MarketData/Symbols/SymbolSentiment/)

To use this signal, LedgerQuant must start recording observations as updates arrive, including `observed_at`, `ingested_at`, `available_at`, symbol, source and validity status. Today's percentage cannot reconstruct observations from before collection began. Evaluations requiring this feature must start with the first reliable recorded observation unless a separate archive is documented.

### News data and news-derived sentiment

Raw news and event records are source evidence. Examples include central-bank statements, CPI releases, geopolitical event records and news articles. Their existence, wording, revisions and decision-time availability are measured independently of any sentiment field or later interpretation. An article's publication timestamp alone does not establish when LedgerQuant or a provider first had access to it. A vendor may return a source item and computed sentiment in one response; LedgerQuant still treats them as separate records with separate provenance and availability.

cTrader's example of reading news in a cBot retrieves it from an **external** NewsData API over the network. The example does not document a built-in cTrader news archive from which LedgerQuant can retrieve history. [cTrader Algo: network access](https://help.ctrader.com/ctrader-algo/how-tos/all-algos/use-network-access/)

| Source or product | Advertised or documented history and content | Important limitation for LedgerQuant |
| --- | --- | --- |
| **GDELT 1.0 GKG** | Begins 1 April 2013; daily news-derived metadata, including themes and emotions. [GDELT: data](https://www.gdeltproject.org/data.html) | Metadata and annotations are not a licensed full-text news archive. Daily processing affects decision-time availability. |
| **GDELT 2.0 Events / GKG** | Began 19 February 2015, with event records, news-derived metadata and tone updates about every 15 minutes. [GDELT: 2.0 launch](https://blog.gdeltproject.org/gdelt-2-0-our-global-world-in-realtime/), [GDELT: data](https://www.gdeltproject.org/data.html) | Event date, article publication date and dataset update time differ. The start date does not guarantee coverage for a specific FX instrument, article or source. |
| **Alpha Vantage `NEWS_SENTIMENT`** | Historical finance news and sentiment can be filtered by time and forex ticker, including `FOREX:USD`; its API documents no universal earliest date. [Alpha Vantage: API documentation](https://www.alphavantage.co/documentation/#news-sentiment) | Query parameters do not prove 2020 coverage. Check actual results, response limits, article identifiers, source rights and sentiment timestamp/method under the intended plan. |
| **Event Registry / NewsAPI.ai** | Advertises an article archive since January 2014, plus events, categories, entities and sentiment. [NewsAPI.ai: archive](https://newsapi.ai/data-mining), [API documentation](https://newsapi.ai/documentation?tab=searchEvents) | Article and inferred event are different objects: an event date can differ from reporting dates. Verify 2020 retrieval, full-text and redistribution rights, revision behavior and archive-query allowance for the chosen subscription. |
| **RavenPack News Analytics** | Advertises over 20 years of historical archives with financial news, entity/event tagging, relevance, novelty and sentiment analytics. [RavenPack: research data](https://marketing-prod.ravenpack.com/solutions/research/wrds), [News Analytics](https://www.ravenpack.com/products/edge/data/news-analytics) | Product, license and source coverage determine which 2020 records and fields are available. Check FX and macro relevance, timestamp precision, historical methodology changes, raw-text rights and commercial terms before selection. |
| **NewsAPI.org `everything`** | Published plans allow about one month of history for Developer use and up to five years on Business/Advanced; results contain article metadata and a short content excerpt, not full text. [NewsAPI.org: pricing](https://newsapi.org/pricing), [Everything endpoint](https://newsapi.org/docs/endpoints/everything) | Under the published standard plans in October 2026, a rolling five-year window does not reach 2020. Enterprise terms would need separate verification; this is a supplement for recent headlines, not a verified 2020 archive. |

Locally computed news sentiment is a separate derived dataset. Its historical depth can extend only as far back as lawfully accessible source material with trustworthy timestamps, but a score computed now was not itself available at the historical decision time. Record its source artifact and revision, model/prompt versions, `scored_at` and actual `available_at`; do not silently present a retrospective score as a live historical observation.

These are candidate sources, not selected production feeds. For a 2020 research start, GDELT and Event Registry merit first coverage probes for events and article metadata; Alpha Vantage merits a small FX-specific response probe; RavenPack merits a license and sample-data assessment if financial relevance justifies it. This is a proposed evaluation order, not a finding that their signals have economic value. NewsAPI.org's published standard archive window makes it a lower-priority 2020 backfill candidate. No source above currently establishes LedgerQuant's earliest usable news or sentiment observation because access, instruments, rights and point-in-time timestamps have not been measured.

### Macroeconomic releases and vintage data

**FRED / ALFRED is a distinct macro source, not a news or sentiment provider.** FRED normally presents the latest revised value; ALFRED's real-time periods and vintage dates support asking what value was published or revised by a historical date. A series can contain decades of observation dates without having equally deep, complete vintage history. Select each series explicitly and inspect its release calendar, first available vintage, revisions and timestamp granularity before using it at a trading decision time. [FRED versus ALFRED](https://fred.stlouisfed.org/docs/api/fred/fred_vs_alfred.html), [real-time periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html), [vintage dates](https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html)

For CPI or another scheduled release, keep the original issuing agency's release artifact and timestamp separate from the ALFRED value vintage. A vintage date is not necessarily the intraday instant at which a trader could first observe the number. The series ID, unit, seasonal adjustment, observation period, release vintage, retrieval time and provider/source contract all belong in the record.

### Measure news coverage

For each candidate provider and relevant market, retrieve monthly counts and samples from 2020 through the present before assuming usable coverage. Check volume, languages, source mix, duplicates, deleted or revised articles, identifiers, missing relevant events, pagination limits and retrieval cost. Record at least `source_id`, `article_id`, `published_at`, the provider's first-seen time if available, `ingested_at`, `available_at`, revision ID and usage rights. For vendor sentiment, also record the linked source artifact, target entity or currency, score definition, method/version, `scored_at` and the time that score was first accessible. Explicitly flag providers that **do not** supply a first-seen time: publication time alone is insufficient evidence that the text or score was available then. Measure scheduled macro releases and ALFRED vintages by series and release, separately from article counts.

## Implications for the research plan

1. **Extend the IC Markets measurement.** January 2020 server ticks are confirmed for the tested EURUSD and GBPUSD account/symbol combinations. Measure monthly coverage, server identity, additional symbols, gaps and direct extraction limits before defining development and validation windows. Retain raw data, test time, source and gap report as auditable provenance.
2. **Distinguish datasets in evaluation.** External historical ticks may support research if broker history is short, but record the source change and validate costs and execution separately against IC Markets observations.
3. **Start prospective collection early.** Recording broker ticks, news and cTrader sentiment now builds a future point-in-time dataset. Do not use cTrader sentiment in historical tests until a real historical series exists.
4. **Select news, vendor sentiment and macro sources independently after measuring coverage.** Fix source rights, timestamps, field-level history and revision handling before any of them influence decisions or evaluations. Keep retrospectively calculated sentiment separate from signals that were actually available in real time.

**Open finding:** The earliest retrievable IC Markets tick for each access method, complete year-by-year tick coverage, and the earliest usable raw news, vendor sentiment and macro vintage for the chosen instruments still require further measurement.
