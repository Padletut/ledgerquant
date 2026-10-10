# Prospective shadow Executor bootstrap

**Status (10 October 2026):** Implemented as a manual, non-trading slice.
Migration `0005_shadow_decisions` was applied to the running database after a
private backup; capture and PostgreSQL remained healthy. No model invocation,
prospective decision or economic evaluation has been run. The existing capture
database contains live broker ticks, but weekend quotes are stale. This is not
an automated schedule or an authorization to trade. The decision contract is
`shadow_executor/2`, which lets the Executor abstain or wait without inventing a setup;
no opportunity had been registered under version 1, and the runner refuses any
opportunity whose recorded contract version differs.

The operator registers an opportunity **before** its scheduled UTC time. The
runner records a `STARTED` event before calling the pinned model and one `FINAL`
event afterward. Repeating `run` never sends a second request. An interrupted
`STARTED` without `FINAL` is reported as `STARTED_UNCERTAIN` and requires an
operator review; it is not retried automatically. A missed slot, no quote,
stale quote, invalid model result and `NO_SIGNAL` remain in the population.
The model receives only symbol, four sampled bid/ask quotes, timestamps and
opaque observation IDs. Feed and account identity stay in PostgreSQL, outside
the provider payload. It cannot call the broker or issue an order.

## Prepare and inspect

Migration `0005_shadow_decisions` creates append-only `decision` tables and
does not alter the capture tables. It is already applied on the local stack;
other deployments must apply it through their normal Alembic migration job
after a backup. `deploy/init_secrets.py` creates the ignored
`credentials/shadow-worker.pwd` without replacing it. Provision the restricted
worker role with the migration service; this was completed on the local stack:

```bash
docker compose -f deploy/compose.yaml -f deploy/compose.shadow.yaml run --rm migrate \
  python -m ledgerquant.decision.cli provision-worker \
  --password-file /run/secrets/shadow_worker_password
```

The role can read capture observations and bindings, read shadow records and
insert shadow opportunities/events. It cannot write capture rows or update
decision records. Choose one feed from the private binding
table; do not copy its ID or account metadata into a public report. Check the
feed's most recent tick and `received_at` before scheduling. The first pilot
uses one explicitly selected CFD symbol, a 60-minute quote-outcome horizon,
a 5-minute proposal expiry and a 10-second maximum age for the latest quote.
These are **bootstrap measurement settings**, not a discovered trading rule or
a profitable-payoff claim. No quote-outcome evaluator is implemented yet.

Run commands from the repository root. The Compose overlay is manual and
requires the existing local API-key secret. `schedule` does not call OpenAI:

```bash
docker compose -f deploy/compose.yaml -f deploy/compose.shadow.yaml run --rm shadow \
  schedule --feed-id "$PRIVATE_FEED_ID" --symbol EURUSD \
  --at 2026-10-12T08:00:00+00:00 \
  --profile /run/config/model-profile.json
```

Keep the returned opportunity UUID. Schedule before that time. `run` must
start no more than 120 seconds after it; late attempts are recorded as
`MISSED` without a model call. `run` sends the assembled quote context to the
configured OpenAI model **only when the latest eligible quote is fresh**:

```bash
docker compose -f deploy/compose.yaml -f deploy/compose.shadow.yaml run --rm shadow \
  run --id OPPORTUNITY_UUID
docker compose -f deploy/compose.yaml -f deploy/compose.shadow.yaml run --rm shadow \
  show --id OPPORTUNITY_UUID
```

The profile is pinned in the opportunity; a different provider profile or
instruction hash is refused. The request has a local USD 1 upper bound using
uncached input and maximum output prices. Provider transport errors remain
uncertain; neither a timeout nor a `STARTED` record justifies another call.
The operator should inspect exact input, response, latency and source times
before interpreting a decision. The `show` command reads the persisted events
and includes full quote and provider content, so treat its output as private.

## Evidence limits

- The scheduler is manual. Only registered slots form this slice's opportunity
  population; a missed registration is not automatically counted. Do not claim
  continuous coverage or statistical performance from it.
- Context is assembled from committed rows at invocation time. The conservative
  visibility time is the read completion time because the capture table's
  current `available_at` can precede commit. This is a prospective read, not a
  historical point-in-time replay.
- Quotes at approximately now, 5, 15 and 30 minutes provide a bounded price
  context. Missing samples remain absent. News, sentiment, account state,
  positions, costs and RAG are not supplied to the first Executor.
- The typed result (`shadow_executor/2`) is `NO_SIGNAL`, `WAIT` or a
  `LONG`/`SHORT` proposal, not a broker order. `NO_SIGNAL` carries nothing and
  needs no justification; an optional short note may be recorded. `WAIT` states
  what kind of thing it waits for (`EVENT`, `CONFIRMATION`, `CONDITIONS` or
  `CLARITY`), what exactly, and when to look again; this slice records it but
  schedules no recheck. A proposal must carry a setup with thesis, cited observation IDs,
  invalidation, uncertainty and the fixed horizon/expiry. A decision carrying
  fields that belong to another action is recorded as `INCONSISTENT_DECISION`.
  There is no fill, realized P/L or independent payoff evidence.
- Repeated calls on an existing opportunity return its recorded state. A
  `STARTED_UNCERTAIN` call is never silently replayed. Manual operational
  review is needed before treating that slot as resolved.
