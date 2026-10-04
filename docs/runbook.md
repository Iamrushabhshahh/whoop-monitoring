# Runbook

Start every check with `make doctor`.

## Token refresh failed / `no tokens stored`

Cause: the refresh token is invalid. Two processes refreshed at the same time, or you revoked
access in the WHOOP app.

1. Stop the collector: `docker compose stop collector`.
2. Run `make login`.
3. Start the collector: `make up`.

## Many `whoop.request.rate_limited` events

Cause: more than 100 requests/min or 10,000/day for the app.

1. Look at `ratelimit_remaining` on the Collector Health dashboard.
2. Do not run many backfills at the same time.
3. Increase `SYNC_INTERVAL_SECONDS` if needed.

## Data is missing for a day

1. In Logs, run `SELECT * FROM "whoop_sleep" WHERE local_date = '2026-10-04'`.
2. If you see only `PENDING_SCORE` rows, WHOOP has not scored it yet. Wait.
3. If you see no rows, run `make backfill SINCE=2026-10-03`. The engine re-reads the range
   and writes only versions that it did not send before.

## OpenObserve says "Too old data"

Cause: `ZO_INGEST_ALLOWED_UPTO` is at the default (5 hours).
Fix: restart OpenObserve with `ZO_INGEST_ALLOWED_UPTO=87600`. Then run the backfill again.

## Alert provisioning fails with "SSRF guard"

Cause: OpenObserve blocks alert destinations on private hosts.
Fix: use a public webhook URL (Slack, Discord), or start OpenObserve with
`ZO_SKIP_SSRF_CHECKS=true` (local machines only).

## Re-load everything from zero

```bash
docker compose stop collector
rm data/state.db                     # forgets watermarks and sent keys
# optional: delete the whoop_* streams in OpenObserve → Streams
make backfill SINCE=2023-01-01
make up
```

## Rotate the client secret

1. Generate a new secret in the WHOOP developer dashboard.
2. Update `WHOOP_CLIENT_SECRET` in `.env`.
3. `docker compose up -d collector` to reload it. Existing tokens stay valid.

## A dashboard shows 0 or old numbers

Cause: the OpenObserve UI serves cached panel results.
Fix: click the refresh button (top right) on the dashboard. To confirm the data, run the panel's
SQL in **Logs**.
