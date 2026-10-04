"""structlog setup. One JSON line per event, with trace context and redaction.

Pipeline: structlog -> stdlib logging -> (stdout handler, OTel handler -> OpenObserve).
See LOGGING.md for the field schema.
"""

import copy
import logging
import sys
from typing import Any

import structlog
from opentelemetry import trace

from whoopmon.config import Settings
from whoopmon.observability.redact import redact_processor, scrub

# Third-party loggers that log request URLs or are noisy at INFO.
_QUIET = ("httpx", "httpcore", "urllib3", "opentelemetry", "uvicorn.access")


def add_trace_context(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    ctx = trace.get_current_span().get_span_context()
    if ctx.is_valid:
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict


_PRIMITIVES = (str, int, float, bool)
# Set by structlog's stdlib bridge; not useful as OTel attributes.
_STRUCTLOG_INTERNALS = ("_logger", "_name", "_from_structlog")
# OTel adds these itself (severity, timestamp, trace context).
_SKIP_FIELDS = frozenset({"event", "level", "timestamp", "trace_id", "span_id"})


class OTelAttributesFilter(logging.Filter):
    """Turn a structlog event dict into OTel log attributes.

    Body = the event name (e.g. `sync.run.finished`); every other field becomes an
    attribute, so OpenObserve stores it as its own column. Works on a copy, so the
    stdout handler still sees the original record.
    """

    def filter(self, record: logging.LogRecord) -> logging.LogRecord:  # type: ignore[override]
        out = copy.copy(record)
        for name in _STRUCTLOG_INTERNALS:
            out.__dict__.pop(name, None)
        if isinstance(out.msg, dict):
            event = dict(out.msg)
            out.msg, out.args = str(event.get("event", "")), ()
            for key, value in event.items():
                if key in _SKIP_FIELDS or value is None:
                    continue
                setattr(out, key, value if isinstance(value, _PRIMITIVES) else str(value))
        else:
            out.msg, out.args = scrub(out.getMessage()), ()
        return out


def setup_logging(settings: Settings, otel_handler: logging.Handler | None = None) -> None:
    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        add_trace_context,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        redact_processor,
    ]

    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    renderer: Any = (
        structlog.processors.JSONRenderer()
        if settings.log_format == "json"
        else structlog.dev.ConsoleRenderer()
    )
    stdout = logging.StreamHandler(sys.stdout)
    stdout.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
        )
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(stdout)
    if otel_handler is not None:
        otel_handler.addFilter(OTelAttributesFilter())
        root.addHandler(otel_handler)
    root.setLevel(settings.log_level.upper())
    for name in _QUIET:
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.stdlib.get_logger(name)  # type: ignore[no-any-return]
