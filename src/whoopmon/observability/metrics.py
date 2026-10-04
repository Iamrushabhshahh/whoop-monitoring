"""Collector metrics. Names follow OTel semantic style: whoopmon.<area>.<thing>."""

from opentelemetry import metrics

_meter = metrics.get_meter("whoopmon")

api_requests = _meter.create_counter(
    "whoopmon.api.requests", description="WHOOP API requests by resource and HTTP status"
)
api_latency = _meter.create_histogram(
    "whoopmon.api.duration", unit="ms", description="WHOOP API request latency"
)
rate_limited = _meter.create_counter(
    "whoopmon.api.rate_limited", description="429 responses from WHOOP"
)
ratelimit_remaining = _meter.create_gauge(
    "whoopmon.api.ratelimit_remaining", description="Last X-RateLimit-Remaining value"
)
records_fetched = _meter.create_counter(
    "whoopmon.records.fetched", description="Records read from WHOOP"
)
records_shipped = _meter.create_counter(
    "whoopmon.records.shipped", description="Records written to OpenObserve"
)
token_refreshes = _meter.create_counter(
    "whoopmon.auth.token_refreshes", description="OAuth token refresh attempts by outcome"
)
sync_runs = _meter.create_counter("whoopmon.sync.runs", description="Sync runs by outcome")
sync_duration = _meter.create_histogram(
    "whoopmon.sync.duration", unit="ms", description="Duration of one sync run"
)
webhook_events = _meter.create_counter(
    "whoopmon.webhook.events", description="Webhook events by type and outcome"
)
