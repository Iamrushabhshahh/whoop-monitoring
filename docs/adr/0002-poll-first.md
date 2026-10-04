# ADR 0002 — Polling first, webhooks optional

- Status: accepted
- Date: 2026-10-05

## Context

WHOOP sends webhooks for recovery, sleep and workout, but not for cycles. Webhooks need a
public HTTPS URL. WHOOP retries a failed webhook only 5 times in about one hour.

## Decision

The scheduler polls every 15 minutes and re-reads the last 72 hours. Webhooks are an extra
fast path that uses the same engine code (`handle_webhook`).

## Consequences

- The system works with no open port. Cycles (day strain, steps) are always complete.
- Missed webhooks heal on the next poll.
- Cost: about 770 requests per day, under 8 % of the daily limit.
