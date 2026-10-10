# News capture

**Status (11 October 2026):** Running in the capture Compose stack as the `news`
service. Migrations `0006_news` and `0007_macro` were applied to the running
database, each after a private backup. A GDELT backfill from 1 September 2025 was
started on 10 October. FRED/ALFRED macro data and its release calendar have been
captured since 11 October.

## What is captured

| Source | What | How often |
| --- | --- | --- |
| `gdelt_gkg` | GDELT 2.0 GKG records inside the FX and gold capture scope: URL, page title, source name, matched themes and organizations, all themes and organizations (truncated), tone | Every 15-minute batch |
| `fed_press` | Federal Reserve press releases (RSS) | Polled every 5 minutes |
| `ecb_press` | ECB press releases (RSS) | Polled every 5 minutes |
| `boe_news` | Bank of England news (RSS) | Polled every 5 minutes |
| `fred_release_dates` | FRED release calendar for the releases of the tracked series, from 1 September 2025 including scheduled future dates | Every 6 hours |
| `fred_observations` | ALFRED vintages of the tracked series: every value with the date it became current, observations from 2024 | Every 6 hours |

The GDELT capture scope (`gdelt_fx_gold_v1`) keeps a record when it has an
economic theme relevant to currencies, rates, inflation, central banks, debt,
trade, oil or equities, names a major central bank or the IMF, or has a title
mentioning gold, the dollar, euro, sterling, inflation, rates, central banks,
key releases, yields, currencies, recession or tariffs. In measured weekday
batches this kept about 13 % of records. It is a capture scope, not a relevance
judgement for trading: GDELT is broad, many kept records are only loosely
related, and the agents' context selection decides what is shown to them. The
version is stored with every item; a changed scope gets a new version.

No article text is stored, only the metadata above and the link.

The FRED series set (`fred_macro_v1`) covers US CPI and core CPI, core PCE,
payrolls, unemployment, initial claims, retail sales, real GDP, the Fed funds
target (upper), the 10-year Treasury yield, the broad dollar index, the ECB
deposit rate, euro-area HICP and SONIA. The release calendar is derived from
the releases these series belong to. A changed set gets a new version. The FRED
API key is read from the `fred_api_key` secret (`credentials/fred-api.key`), sent
as a request parameter and never stored in the fetch log.

## Time fields

- `published_at`: the provider's time. For GDELT this is the GKG batch time, not
  the article's publication time. For RSS it is the item's `pubDate` or Atom
  date.
- `first_seen_at`: when LedgerQuant first stored the item.
- `available_at`: equal to `first_seen_at` for live capture. Empty for
  backfilled items, because downloading an old batch now does not show when it
  could first have been read.
- `backfilled`: true for items from the backfill command.

Macro release dates are **dates without a time of day**. Series updated every
business day (the Fed funds target, ECB rates, SONIA, Treasury yields, the
dollar index) have a release date for every update; those are data updates, not
policy meetings. Macro observations keep `realtime_start`, the date a value
became current in ALFRED. The source clamps it to the query start (1 September
2025), so the earliest vintage means "known by then", not "first published
then". A vintage ends where the next one for the same observation starts.

Items are unique per source and source item ID. An item seen again keeps its
first record; later changes to an RSS item are not tracked. All news tables are
append-only.

Every request is recorded in `news.fetches` with its HTTP status, error, size,
SHA-256 and counts. A GDELT batch that returns 404 is recorded as missing and
not requested again. The live collector catches up on the last 6 hours of GDELT
batches after an interruption; caught-up items get their real fetch time as
`available_at`.

## Operate

Start or update the service together with the capture stack:

```bash
docker compose -f deploy/compose.yaml up -d --build news
docker logs --tail 20 ledgerquant-capture-news-1
```

Backfill GDELT for a past interval. The command is resumable and stops at the
latest published batch:

```bash
docker compose -f deploy/compose.yaml run -d --build --name lq-news-backfill news \
  python -m ledgerquant.news.backfill --start 2025-09-01 --end 2026-10-11
docker logs --tail 5 lq-news-backfill
docker rm lq-news-backfill   # after it has finished
```

Check what has been captured:

```sql
SELECT source, backfilled, count(*), min(published_at), max(published_at)
FROM news.items GROUP BY 1, 2 ORDER BY 1, 2;
SELECT source, http_status, error, count(*) FROM news.fetches GROUP BY 1, 2, 3;
```

## Limits

- The FRED calendar gives release dates without times and does not list FOMC,
  ECB or BoE policy meetings. UK CPI is not covered: the OECD series in FRED
  stopped updating in September 2025.
- No primary statistics releases (for example BLS CPI) yet; BLS refused scripted
  access in an earlier probe.
- RSS feeds only list recent items, so central-bank releases before 10 October
  2026 are not backfilled; GDELT covers news about them.
- GDELT batch gaps exist (see [data availability](../data/DATA_AVAILABILITY.md));
  missing batches stay visible as 404 fetches.
- Usage rights for stored metadata and linked articles have not been reviewed.
