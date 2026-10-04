"""Webhook receiver. Verifies, de-duplicates, queues, and answers 204 at once.

WHOOP wants a 2xx within about one second, so the record fetch runs on a worker thread.
"""

import queue
import threading
from typing import Any

from fastapi import FastAPI, Request, Response

from whoopmon.config import Settings
from whoopmon.observability import get_logger
from whoopmon.observability.metrics import webhook_events
from whoopmon.sync.engine import SyncEngine
from whoopmon.sync.state import StateStore
from whoopmon.webhook.signature import verify

log = get_logger(__name__)


def create_app(settings: Settings, engine: SyncEngine, state: StateStore) -> FastAPI:
    app = FastAPI(title="whoopmon webhook", docs_url=None, redoc_url=None)
    jobs: queue.Queue[dict[str, Any]] = queue.Queue()
    secret = settings.whoop_client_secret.get_secret_value()

    def worker() -> None:
        while True:
            event = jobs.get()
            try:
                engine.handle_webhook(event["type"], str(event["id"]), event["trace_id"])
                webhook_events.add(1, {"type": event["type"], "outcome": "processed"})
            except Exception:
                webhook_events.add(1, {"type": event["type"], "outcome": "error"})
                log.exception("webhook.event.failed", type=event["type"])
            finally:
                jobs.task_done()

    threading.Thread(target=worker, daemon=True, name="webhook-worker").start()

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/o2-alert", status_code=204)
    async def o2_alert(request: Request) -> Response:
        """OpenObserve alert destination. Logs the alert so it shows in whoopmon_app."""
        try:
            payload = await request.json()
        except ValueError:
            payload = {"raw": (await request.body()).decode(errors="replace")[:2000]}
        log.warning(
            "alert.received",
            alert=payload.get("alert"),
            stream=payload.get("stream"),
            count=payload.get("count"),
            alert_rows=str(payload.get("rows", ""))[:1000],
        )
        return Response(status_code=204)

    @app.post("/webhook", status_code=204)
    async def webhook(request: Request) -> Response:
        body = await request.body()
        if not verify(
            secret,
            request.headers.get("X-WHOOP-Signature-Timestamp"),
            request.headers.get("X-WHOOP-Signature"),
            body,
        ):
            webhook_events.add(1, {"type": "unknown", "outcome": "bad_signature"})
            log.warning("webhook.signature.invalid")
            return Response(status_code=401)

        event = await request.json()
        if not state.remember_webhook(event["trace_id"]):
            webhook_events.add(1, {"type": event["type"], "outcome": "duplicate"})
            log.info(
                "webhook.event.duplicate", type=event["type"], whoop_trace_id=event["trace_id"]
            )
            return Response(status_code=204)

        jobs.put(event)
        log.info("webhook.event.queued", type=event["type"], whoop_trace_id=event["trace_id"])
        return Response(status_code=204)

    return app
