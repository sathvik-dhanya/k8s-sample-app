"""Configure root and Flask app loggers to emit JSON."""

import logging
import sys

from opentelemetry import trace
from pythonjsonlogger.json import JsonFormatter

LOG_LEVEL = logging.INFO
_JSON_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


class TraceContextFilter(logging.Filter):
    """Add the active OpenTelemetry trace context to structured log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Attach trace and span IDs when the record is emitted in a span."""
        context = trace.get_current_span().get_span_context()
        if context.is_valid:
            record.trace_id = format(context.trace_id, "032x")
            record.span_id = format(context.span_id, "016x")
        return True


def configure_json_logging(app_logger: logging.Logger) -> None:
    """Configure Flask logs as JSON and allow other handlers to receive them."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(_JSON_FORMAT))
    handler.addFilter(TraceContextFilter())

    # Replace any default handlers Flask installed
    app_logger.handlers.clear()
    app_logger.addHandler(handler)
    app_logger.setLevel(LOG_LEVEL)
    app_logger.propagate = True


def configure_otel_logging(handler: logging.Handler) -> None:
    """Serialize OTLP log bodies as JSON while retaining fields as attributes."""
    handler.setFormatter(JsonFormatter(_JSON_FORMAT))
    handler.addFilter(TraceContextFilter())
