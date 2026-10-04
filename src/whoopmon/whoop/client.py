"""HTTP client for the WHOOP Developer API v2.

Handles: bearer auth with refresh on 401, the 100/min + 10k/day rate limits (429),
retries with exponential backoff on 5xx and network errors, and nextToken pagination.
"""

import random
import time
from collections.abc import Iterator
from datetime import datetime
from typing import Any

import httpx
from opentelemetry import trace

from whoopmon.auth.oauth import TokenManager
from whoopmon.config import Settings
from whoopmon.observability import get_logger
from whoopmon.observability.metrics import (
    api_latency,
    api_requests,
    rate_limited,
    ratelimit_remaining,
)

log = get_logger(__name__)
tracer = trace.get_tracer(__name__)

PAGE_LIMIT = 25  # WHOOP maximum


class WhoopAPIError(RuntimeError):
    def __init__(self, status: int, path: str) -> None:
        super().__init__(f"WHOOP API {status} on {path}")
        self.status = status
        self.path = path


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class WhoopClient:
    def __init__(
        self,
        settings: Settings,
        tokens: TokenManager,
        transport: httpx.BaseTransport | None = None,
        sleep: Any = time.sleep,
    ) -> None:
        self.settings = settings
        self.tokens = tokens
        self._sleep = sleep
        self._http = httpx.Client(
            base_url=settings.whoop_api_base,
            timeout=settings.http_timeout_seconds,
            transport=transport,
            headers={
                "User-Agent": "whoopmon/0.1 (+https://github.com/Iamrushabhshahh/whoop-monitoring)"
            },
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "WhoopClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- core request ---------------------------------------------------------

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """GET one resource. Returns None on 404."""
        refreshed = False
        attempt = 0
        with tracer.start_as_current_span("whoop.request", attributes={"http.route": path}) as span:
            while True:
                attempt += 1
                token = self.tokens.access_token()
                started = time.monotonic()
                try:
                    resp = self._http.get(
                        path, params=params, headers={"Authorization": f"Bearer {token}"}
                    )
                except httpx.TransportError as exc:
                    if attempt > self.settings.max_retries:
                        raise
                    self._backoff(attempt, path, reason=type(exc).__name__)
                    continue

                duration_ms = (time.monotonic() - started) * 1000
                attrs = {"route": path.split("/{")[0], "status": resp.status_code}
                api_requests.add(1, attrs)
                api_latency.record(duration_ms, attrs)
                remaining = resp.headers.get("X-RateLimit-Remaining")
                if remaining and remaining.isdigit():
                    ratelimit_remaining.set(int(remaining))
                span.set_attribute("http.status_code", resp.status_code)
                log.debug(
                    "whoop.request.completed",
                    path=path,
                    status=resp.status_code,
                    duration_ms=round(duration_ms),
                    ratelimit_remaining=remaining,
                    attempt=attempt,
                )

                if resp.status_code == 200:
                    return resp.json()  # type: ignore[no-any-return]
                if resp.status_code == 404:
                    return None
                if resp.status_code == 401 and not refreshed:
                    log.warning("whoop.request.unauthorized", path=path)
                    refreshed = True
                    self.tokens.access_token(force_refresh=True)
                    continue
                if resp.status_code == 429:
                    wait = self._reset_seconds(resp)
                    rate_limited.add(1)
                    log.warning("whoop.request.rate_limited", path=path, wait_s=wait)
                    if attempt > self.settings.max_retries:
                        raise WhoopAPIError(429, path)
                    self._sleep(wait)
                    continue
                if resp.status_code >= 500 and attempt <= self.settings.max_retries:
                    self._backoff(attempt, path, reason=f"http_{resp.status_code}")
                    continue
                log.error("whoop.request.failed", path=path, status=resp.status_code)
                raise WhoopAPIError(resp.status_code, path)

    @staticmethod
    def _reset_seconds(resp: httpx.Response) -> float:
        raw = resp.headers.get("X-RateLimit-Reset", "")
        try:
            return max(1.0, float(raw.split(",")[0])) + 1
        except ValueError:
            return 60.0

    def _backoff(self, attempt: int, path: str, reason: str) -> None:
        wait = min(60.0, 2 ** (attempt - 1)) + random.uniform(0, 0.5)  # noqa: S311
        log.warning(
            "whoop.request.retrying",
            path=path,
            attempt=attempt,
            wait_s=round(wait, 2),
            reason=reason,
        )
        self._sleep(wait)

    # -- collections ----------------------------------------------------------

    def paginate(
        self, path: str, start: datetime | None = None, end: datetime | None = None
    ) -> Iterator[dict[str, Any]]:
        params: dict[str, Any] = {"limit": PAGE_LIMIT}
        if start:
            params["start"] = _iso(start)
        if end:
            params["end"] = _iso(end)
        while True:
            page = self.get(path, params)
            if not page:
                return
            yield from page.get("records", [])
            next_token = page.get("next_token") or page.get("nextToken")
            if not next_token:
                return
            params["nextToken"] = next_token
