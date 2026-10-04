"""Sync engine: read WHOOP records, skip versions already shipped, write the rest.

A run re-reads `sync_lookback_hours` before the watermark, because WHOOP scores
sleep and recovery late (PENDING_SCORE -> SCORED) and users can edit records.
The `sent` table makes the re-read cheap: unchanged versions are not written again.
"""

import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from opentelemetry import trace

from whoopmon.config import Settings
from whoopmon.observability import get_logger
from whoopmon.observability.metrics import records_fetched, sync_duration, sync_runs
from whoopmon.sinks.openobserve import OpenObserveSink
from whoopmon.sync.state import StateStore
from whoopmon.transform.flatten import parse_ts, to_row, tombstone
from whoopmon.whoop.client import WhoopClient
from whoopmon.whoop.resources import (
    RECOVERY,
    SNAPSHOTS,
    TIME_SERIES,
    WEBHOOK_RESOURCES,
    Resource,
)

log = get_logger(__name__)
tracer = trace.get_tracer(__name__)


def new_run_id() -> str:
    return f"{int(time.time())}-{secrets.token_hex(4)}"


@dataclass
class ResourceResult:
    fetched: int = 0
    shipped: int = 0
    pending: int = 0


@dataclass
class RunResult:
    run_id: str
    resources: dict[str, ResourceResult] = field(default_factory=dict)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class SyncEngine:
    def __init__(
        self, settings: Settings, client: WhoopClient, sink: OpenObserveSink, state: StateStore
    ) -> None:
        self.settings = settings
        self.client = client
        self.sink = sink
        self.state = state

    # -- public API -----------------------------------------------------------

    def run(self, since: datetime | None = None, until: datetime | None = None) -> RunResult:
        """Sync every resource. `since` forces a start time (backfill)."""
        run_id = new_run_id()
        started = datetime.now(UTC)
        result = RunResult(run_id)
        self.state.start_run(run_id, started)
        structlog.contextvars.bind_contextvars(run_id=run_id)
        t0 = time.monotonic()
        mode = "backfill" if since else "incremental"
        with tracer.start_as_current_span("sync.run", attributes={"run_id": run_id, "mode": mode}):
            log.info("sync.run.started", mode=mode, since=since.isoformat() if since else None)
            try:
                for resource in TIME_SERIES:
                    result.resources[resource.name] = self.sync_resource(resource, since, until)
                for resource in SNAPSHOTS:
                    result.resources[resource.name] = self.sync_snapshot(resource)
            except Exception as exc:
                result.error = f"{type(exc).__name__}: {exc}"
                log.exception("sync.run.failed")
            finally:
                outcome = "success" if result.ok else "failure"
                ms = (time.monotonic() - t0) * 1000
                sync_runs.add(1, {"outcome": outcome, "mode": mode})
                sync_duration.record(ms, {"mode": mode})
                self.state.finish_run(run_id, datetime.now(UTC), outcome, result.error or "")
                log.info(
                    "sync.run.finished",
                    outcome=outcome,
                    duration_ms=round(ms),
                    **{f"{k}_shipped": v.shipped for k, v in result.resources.items()},
                )
                structlog.contextvars.unbind_contextvars("run_id")
        return result

    def sync_resource(
        self, resource: Resource, since: datetime | None = None, until: datetime | None = None
    ) -> ResourceResult:
        res = ResourceResult()
        with tracer.start_as_current_span("sync.resource", attributes={"resource": resource.name}):
            start = since or self._incremental_start(resource)
            records = list(self.client.paginate(resource.path, start=start, end=until))
            res.fetched = len(records)
            records_fetched.add(res.fetched, {"resource": resource.name})
            res.pending = sum(1 for r in records if r.get("score_state") == "PENDING_SCORE")

            res.shipped = self._ship(resource, records)

            newest = max(
                (parse_ts(r[resource.time_field]) for r in records if r.get(resource.time_field)),
                default=None,
            )
            watermark = self.state.get_watermark(resource.name)
            if newest and (watermark is None or newest > watermark):
                self.state.set_watermark(resource.name, newest)
            log.info(
                "sync.resource.completed",
                resource=resource.name,
                start=start.isoformat() if start else None,
                fetched=res.fetched,
                shipped=res.shipped,
                pending_score=res.pending,
            )
        return res

    def sync_snapshot(self, resource: Resource) -> ResourceResult:
        """Body measurements: one record, no time. Ship when values change or once a day."""
        res = ResourceResult()
        record = self.client.get(resource.path)
        if not record:
            return res
        res.fetched = 1
        today = datetime.now(UTC).date().isoformat()
        digest = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()[:16]
        key = f"{today}:{digest}"
        if self.state.unsent(resource.name, [key]):
            row = to_row(resource, record)
            row["record_key"] = key
            res.shipped = self.sink.write(resource.name, [row])
            self.state.mark_sent(resource.name, [key])
        return res

    def handle_webhook(self, event_type: str, record_id: str, trace_id: str) -> int:
        """Process one webhook event. Returns rows shipped."""
        prefix, _, action = event_type.partition(".")
        if prefix not in WEBHOOK_RESOURCES:
            log.warning("webhook.event.unknown_type", type=event_type)
            return 0
        resource, path = WEBHOOK_RESOURCES[prefix]
        with tracer.start_as_current_span(
            "webhook.process", attributes={"event.type": event_type, "whoop.trace_id": trace_id}
        ):
            if action == "deleted":
                return self.sink.write(resource.name, [tombstone(resource, record_id, trace_id)])

            record = self.client.get(path.format(id=record_id))
            if record is None:
                log.warning("webhook.record.not_found", type=event_type, record_id=record_id)
                return 0
            if resource is RECOVERY:
                # v2 recovery events carry the sleep id; recovery is keyed by that sleep's cycle.
                record = self.client.get(f"/v2/cycle/{record['cycle_id']}/recovery")
                if record is None:
                    return 0
            return self._ship(resource, [record])

    # -- internals ------------------------------------------------------------

    def _incremental_start(self, resource: Resource) -> datetime:
        watermark = self.state.get_watermark(resource.name)
        lookback = timedelta(hours=self.settings.sync_lookback_hours)
        if watermark is None:
            # First run without backfill: take the last 30 days.
            return datetime.now(UTC) - timedelta(days=30)
        return watermark - lookback

    def _ship(self, resource: Resource, records: list[dict[str, Any]]) -> int:
        rows = [to_row(resource, r) for r in records]
        by_key = {row["record_key"]: row for row in rows}
        fresh = self.state.unsent(resource.name, by_key)
        if not fresh:
            return 0
        shipped = self.sink.write(resource.name, [by_key[k] for k in sorted(fresh)])
        self.state.mark_sent(resource.name, fresh)
        return shipped
