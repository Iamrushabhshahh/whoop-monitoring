"""Logging, tracing and metrics for the collector."""

from whoopmon.config import Settings
from whoopmon.observability.logging import get_logger, setup_logging
from whoopmon.observability.telemetry import setup_telemetry, shutdown_telemetry

__all__ = ["bootstrap", "get_logger", "shutdown_telemetry"]


def bootstrap(settings: Settings) -> None:
    """Configure telemetry first, then logging, so logs carry trace ids and reach OTLP."""
    handler = setup_telemetry(settings)
    setup_logging(settings, handler)
