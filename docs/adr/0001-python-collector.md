# ADR 0001 — Python collector as one package

- Status: accepted
- Date: 2026-10-05

## Context

We need an OAuth client, an HTTP poller, a small web server for webhooks, and OTel telemetry.
One person runs it on one machine.

## Decision

Use Python 3.12 with `httpx`, `structlog`, the OpenTelemetry SDK, `FastAPI` and `Typer`.
Ship one package (`whoopmon`) with one CLI. The same image runs the collector and the webhook
receiver with different commands.

## Consequences

- One codebase, one test suite, one Docker image.
- The OTel Python SDK sends logs, metrics and traces to OpenObserve with no agent.
- Python is slower than Go, but the workload is under 1,000 requests per day.
