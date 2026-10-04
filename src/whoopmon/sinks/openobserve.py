"""Write rows to OpenObserve with the `_json` bulk ingest API."""

from typing import Any

import httpx
from opentelemetry import trace

from whoopmon.config import Settings
from whoopmon.observability import get_logger
from whoopmon.observability.metrics import records_shipped

log = get_logger(__name__)
tracer = trace.get_tracer(__name__)

BATCH_SIZE = 500


class SinkError(RuntimeError):
    pass


class OpenObserveSink:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings
        self._http = httpx.Client(
            base_url=f"{settings.o2_url}/api/{settings.o2_org}",
            auth=(settings.o2_user, settings.o2_password.get_secret_value()),
            timeout=settings.http_timeout_seconds,
            transport=transport,
        )

    def stream(self, resource_name: str) -> str:
        return f"{self.settings.o2_stream_prefix}{resource_name}"

    def write(self, resource_name: str, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        stream = self.stream(resource_name)
        written = 0
        with tracer.start_as_current_span("openobserve.ingest", attributes={"stream": stream}):
            for i in range(0, len(rows), BATCH_SIZE):
                batch = rows[i : i + BATCH_SIZE]
                resp = self._http.post(f"/{stream}/_json", json=batch)
                if resp.status_code != 200:
                    log.error(
                        "sink.write.failed",
                        stream=stream,
                        status=resp.status_code,
                        body=resp.text[:300],
                    )
                    raise SinkError(f"OpenObserve returned {resp.status_code} for {stream}")
                status = resp.json().get("status", [{}])[0]
                failed = int(status.get("failed", 0))
                if failed:
                    log.error(
                        "sink.write.partial",
                        stream=stream,
                        failed=failed,
                        error=status.get("error"),
                    )
                    raise SinkError(f"{failed} rows rejected by {stream}")
                written += len(batch)
        records_shipped.add(written, {"stream": stream})
        log.info("sink.write.completed", stream=stream, rows=written)
        return written

    def close(self) -> None:
        self._http.close()
