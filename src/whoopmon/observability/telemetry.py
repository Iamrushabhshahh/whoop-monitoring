"""OpenTelemetry setup: traces, metrics and logs go to OpenObserve over OTLP/HTTP."""

import base64
import logging

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from whoopmon import __version__
from whoopmon.config import Settings

APP_LOG_STREAM = "whoopmon_app"

_providers: list[TracerProvider | MeterProvider | LoggerProvider] = []


def setup_telemetry(settings: Settings) -> logging.Handler | None:
    """Install global OTel providers. Returns a stdlib handler that ships logs, or None."""
    if not settings.otel_enabled:
        return None

    token = base64.b64encode(
        f"{settings.o2_user}:{settings.o2_password.get_secret_value()}".encode()
    ).decode()
    headers = {"Authorization": f"Basic {token}"}
    base = f"{settings.o2_url}/api/{settings.o2_org}/v1"
    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.version": __version__,
            "deployment.environment": settings.environment,
        }
    )

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{base}/traces", headers=headers))
    )
    trace.set_tracer_provider(tracer_provider)

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=f"{base}/metrics", headers=headers),
                export_interval_millis=30_000,
            )
        ],
    )
    metrics.set_meter_provider(meter_provider)

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(
            OTLPLogExporter(
                endpoint=f"{base}/logs", headers={**headers, "stream-name": APP_LOG_STREAM}
            )
        )
    )
    _providers.extend([tracer_provider, meter_provider, logger_provider])
    return LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)


def shutdown_telemetry() -> None:
    """Flush everything. Call before the process exits."""
    for provider in _providers:
        provider.shutdown()
    _providers.clear()
