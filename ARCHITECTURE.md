# Architecture

## Components

```mermaid
flowchart LR
  subgraph WHOOP["WHOOP cloud"]
    OA["OAuth server"]
    API["Developer API v2"]
    WH["Webhook sender"]
  end
  subgraph HOST["Your machine"]
    CLI["whoopmon CLI<br/>auth · backfill · provision"]
    COL["collector container · whoopmon serve<br/>scheduler + :8080 /webhook /o2-alert"]
    ST[("data/<br/>tokens.json · state.db")]
    O2["OpenObserve :5080"]
  end
  CLI -->|"login"| OA
  COL -->|"GET records"| API
  CLI --> ST
  COL <--> ST
  WH -->|"POST (via tunnel)"| COL
  COL -->|"_json ingest"| O2
  O2 -->|"alert POST /o2-alert"| COL
  COL -.->|"OTLP"| O2
  CLI -->|"dashboards, alerts API"| O2
```

| Module | Job |
|---|---|
| `auth/` | OAuth login, callback server, token store with file lock and atomic write |
| `whoop/` | HTTP client (auth, 429, retries), pagination, resource catalog |
| `transform/` | Nested record → flat row; event time, local date, hours columns |
| `sinks/` | OpenObserve `_json` bulk ingest |
| `sync/` | Engine (watermarks, de-dup), scheduler, SQLite state |
| `webhook/` | HMAC check, de-dup by `trace_id`, queue, OpenObserve alert receiver |
| `provision/` | Dashboards and alerts as code |
| `observability/` | structlog, OTel traces/metrics/logs, redaction |

## One sync run

```mermaid
sequenceDiagram
  autonumber
  participant S as Scheduler
  participant E as SyncEngine
  participant DB as state.db
  participant W as WHOOP API
  participant O as OpenObserve
  S->>E: run()
  loop cycle, recovery, sleep, workout
    E->>DB: read watermark
    E->>W: GET /v2/... ?start=watermark-72h&limit=25
    W-->>E: records + next_token
    E->>DB: which id@updated_at are new?
    E->>O: POST whoop_<type>/_json (new rows only)
    E->>DB: mark sent, move watermark
  end
  E->>W: GET body measurement
  E->>O: one row per day if changed
  E-->>S: RunResult (logged + metrics + trace)
```

## Key decisions

| Decision | Reason | ADR |
|---|---|---|
| Python, one package, Typer CLI | Small codebase, good OTel and HTTP libraries | [0001](docs/adr/0001-python-collector.md) |
| Poll first, webhooks optional | No cycle webhooks exist; polling needs no public URL | [0002](docs/adr/0002-poll-first.md) |
| Append + `record_key` de-dup, latest-row SQL | OpenObserve has no update; WHOOP re-scores records | [0003](docs/adr/0003-append-and-dedupe.md) |
| `_timestamp` = event time | Time picker filters by when things happened | [0003](docs/adr/0003-append-and-dedupe.md) |

## Failure handling

| Failure | Behaviour |
|---|---|
| 401 | Refresh token once under a file lock, then retry |
| 429 | Wait `X-RateLimit-Reset` + 1 s, then retry (max 5) |
| 5xx / network | Exponential backoff with jitter, max 5 tries |
| OpenObserve rejects rows | Run fails; rows stay "unsent" and go again next run |
| Crash mid-run | Watermark and sent-keys move only after a write succeeds |
