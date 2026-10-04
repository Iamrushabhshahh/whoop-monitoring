# ADR 0003 — Append rows, de-duplicate by version, query the latest

- Status: accepted
- Date: 2026-10-05

## Context

OpenObserve streams are append-only. WHOOP changes records after they appear:
`PENDING_SCORE` → `SCORED`, user edits, deletes.

## Decision

1. Each row has `record_key = record_id@updated_at`.
2. `state.db` keeps the keys already sent. A re-read sends only new versions.
3. Dashboards pick the newest row per `record_id` with `ROW_NUMBER()`.
4. Deletes write a tombstone row with `deleted = true`.
5. `_timestamp` is the event time, so the time picker means "when it happened".
   OpenObserve must run with `ZO_INGEST_ALLOWED_UPTO` large enough for history.

## Consequences

- No duplicate rows from polling. One extra row per real change.
- Queries are a little longer. The dashboards hide this.
- Deleting `state.db` makes the next backfill send everything again (duplicates are still
  hidden by the latest-row query).
