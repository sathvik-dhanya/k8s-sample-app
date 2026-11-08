"""Optional OpenTelemetry providers and request instrumentation."""

import logging
import os
from typing import Any

from opentelemetry import propagate
from opentelemetry.metrics import Observation
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import SpanKind, Status, StatusCode


class Telemetry:
    """Create request instruments and optional OTLP exporters for one Flask app."""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        metric_reader: Any = None,
        span_exporter: Any = None,
        log_exporter: Any = None,
    ) -> None:
        """Set up per-app providers, with injectable readers/exporters for tests."""
        if enabled is None:
            enabled = os.getenv("OTEL_ENABLED", "false").lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        self.enabled = enabled
        self.service_name = os.getenv("OTEL_SERVICE_NAME", "python-app")
        resource = Resource.create(
            {
                SERVICE_NAME: self.service_name,
                "service.instance.id": os.getenv(
                    "OTEL_SERVICE_INSTANCE_ID",
                    os.getenv("HOSTNAME", "local"),
                ),
            }
        )
        endpoint = os.getenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317"
        )

        sampler_ratio = float(os.getenv("OTEL_TRACES_SAMPLER_ARG", "1.0"))
        if not 0 <= sampler_ratio <= 1:
            raise ValueError("OTEL_TRACES_SAMPLER_ARG must be between 0 and 1")
        self.tracer_provider = TracerProvider(
            resource=resource,
            sampler=ParentBased(TraceIdRatioBased(sampler_ratio)),
        )
        if enabled:
            # Batch export keeps collector retries off the request-handling path.
            use_simple_processor = span_exporter is not None
            if span_exporter is None:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                    OTLPSpanExporter,
                )

                span_exporter = OTLPSpanExporter(
                    endpoint=endpoint, insecure=True, timeout=2
                )
            processor = (
                SimpleSpanProcessor(span_exporter)
                if use_simple_processor
                else BatchSpanProcessor(span_exporter)
            )
            self.tracer_provider.add_span_processor(processor)
        self.tracer = self.tracer_provider.get_tracer(__name__)

        metric_readers = []
        if metric_reader is not None:
            metric_readers.append(metric_reader)
        elif enabled:
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
                OTLPMetricExporter,
            )

            metric_readers.append(
                PeriodicExportingMetricReader(
                    OTLPMetricExporter(
                        endpoint=endpoint, insecure=True, timeout=2
                    ),
                    export_interval_millis=5000,
                )
            )
        self.meter_provider = MeterProvider(
            resource=resource, metric_readers=metric_readers
        )
        meter = self.meter_provider.get_meter(__name__)
        # Dotted names and HTTP attributes map to the dashboard's Prometheus names.
        self.request_count = meter.create_counter(
            "http.server.request.count",
            description="Number of HTTP requests handled",
            unit="{request}",
        )
        self.error_count = meter.create_counter(
            "http.server.request.error_count",
            description="Number of HTTP requests resulting in server errors",
            unit="{request}",
        )
        self.request_duration = meter.create_histogram(
            "http.server.request.duration",
            description="HTTP request duration",
            unit="s",
        )
        meter.create_observable_gauge(
            "app.health",
            callbacks=[
                lambda options: [Observation(1, {"status": "healthy"})]
            ],
            description="Application health (1 means healthy)",
            unit="1",
        )

        self.logger_provider = LoggerProvider(resource=resource)
        self.logging_handler = None
        if enabled:
            if log_exporter is None:
                from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
                    OTLPLogExporter,
                )

                log_exporter = OTLPLogExporter(
                    endpoint=endpoint, insecure=True, timeout=2
                )
            self.logger_provider.add_log_record_processor(
                BatchLogRecordProcessor(log_exporter)
            )
            self.logging_handler = LoggingHandler(
                level=logging.INFO, logger_provider=self.logger_provider
            )

    def start_request(self, method: str, route: str, context: Any):
        """Start a server span and continue any trace context from the request."""
        return self.tracer.start_as_current_span(
            f"{method} {route}",
            context=propagate.extract(context),
            kind=SpanKind.SERVER,
        )

    def record_request(
        self, method: str, route: str, status_code: int, duration: float
    ) -> None:
        """Record request count, duration, and 5xx error metrics."""
        attributes = {
            "http.request.method": method,
            "http.route": route,
            "http.response.status_code": status_code,
        }
        self.request_count.add(1, attributes)
        self.request_duration.record(duration, attributes)
        if status_code >= 500:
            self.error_count.add(1, attributes)

    @staticmethod
    def finish_span(span: Any, status_code: int) -> None:
        """Attach the HTTP result and mark server-side failures on the span."""
        span.set_attribute("http.response.status_code", status_code)
        if status_code >= 500:
            span.set_status(Status(StatusCode.ERROR))

    def shutdown(self) -> None:
        """Flush and stop this app's SDK providers and their exporters."""
        if self.logging_handler is not None:
            logging.getLogger().removeHandler(self.logging_handler)
        self.tracer_provider.shutdown()
        self.meter_provider.shutdown()
        self.logger_provider.shutdown()
