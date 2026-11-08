import json
import logging

from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk._logs.export import InMemoryLogExporter, LogExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.sdk.trace.export import SpanExportResult

from app.main import create_app


def _capture_json_logs(app, method: str, path: str) -> list[dict]:
    """Make a test request and return any JSON log records emitted."""
    records: list[dict] = []

    class _Capture(logging.Handler):
        def emit(self, record):
            """Serialize each captured record with the test JSON formatter."""
            records.append(json.loads(self.format(record)))

    from pythonjsonlogger.json import JsonFormatter
    handler = _Capture()
    handler.setFormatter(JsonFormatter())
    app.logger.addHandler(handler)
    try:
        client = app.test_client()
        getattr(client, method)(path)
    finally:
        app.logger.removeHandler(handler)
    return records


def test_index_endpoint_returns_welcome_message():
    """The root route returns the established sample welcome payload."""
    app = create_app()
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["service"] == "python-app"
    assert "Hello" in payload["message"]


def test_access_log_is_valid_json():
    """Every request produces a structured access log with HTTP details."""
    app = create_app()
    logs = _capture_json_logs(app, "get", "/")

    assert len(logs) >= 1
    record = logs[-1]
    assert record["message"] == "request"
    assert record["method"] == "GET"
    assert record["path"] == "/"
    assert record["status"] == 200
    assert "duration_ms" in record


def test_liveness_log_contains_probe_path():
    """The liveness request's structured log retains its path and status."""
    app = create_app()
    logs = _capture_json_logs(app, "get", "/healthz/live")

    record = logs[-1]
    assert record["path"] == "/healthz/live"
    assert record["status"] == 200


def test_liveness_endpoint():
    """The liveness probe continues to report an alive process."""
    app = create_app()
    client = app.test_client()

    response = client.get("/healthz/live")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "alive"
    assert payload["probe"] == "liveness"


def test_readiness_log_contains_probe_path():
    """The readiness request's structured log retains its path and status."""
    app = create_app()
    logs = _capture_json_logs(app, "get", "/healthz/ready")

    record = logs[-1]
    assert record["path"] == "/healthz/ready"
    assert record["status"] == 200


def test_readiness_endpoint():
    """The readiness probe continues to report a ready application."""
    app = create_app()
    client = app.test_client()

    response = client.get("/healthz/ready")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ready"
    assert payload["probe"] == "readiness"


def test_simulation_routes_are_disabled_by_default():
    """Synthetic failure endpoints are not exposed in the default app config."""
    app = create_app(telemetry_enabled=False, simulation_enabled=False)

    assert app.test_client().get("/simulate/error").status_code == 404


def test_simulation_emits_error_metrics_and_trace_correlated_logs():
    """Slow and failing demo requests produce dashboard metrics and logs."""
    reader = InMemoryMetricReader()
    span_exporter = InMemorySpanExporter()
    log_exporter = InMemoryLogExporter()
    app = create_app(
        telemetry_enabled=True,
        simulation_enabled=True,
        metric_reader=reader,
        span_exporter=span_exporter,
        log_exporter=log_exporter,
    )
    client = app.test_client()

    slow_response = client.get("/simulate/slow")
    failure_response = client.get("/simulate/error")
    app.extensions["telemetry"].logger_provider.force_flush()

    assert slow_response.status_code == 200
    assert failure_response.status_code == 503

    metrics_data = reader.get_metrics_data()
    assert all(
        resource_metrics.resource.attributes["service.instance.id"]
        for resource_metrics in metrics_data.resource_metrics
    )
    metrics = {
        metric.name: metric
        for resource_metrics in metrics_data.resource_metrics
        for scope_metrics in resource_metrics.scope_metrics
        for metric in scope_metrics.metrics
    }
    error_points = metrics["http.server.request.error_count"].data.data_points
    assert sum(point.value for point in error_points) == 1
    slow_points = metrics["http.server.request.duration"].data.data_points
    slow_point = next(
        point
        for point in slow_points
        if point.attributes["http.route"] == "/simulate/slow"
    )
    assert slow_point.sum >= 0.5

    failure_span = next(
        span
        for span in span_exporter.get_finished_spans()
        if span.name == "GET /simulate/error"
    )
    failure_log = next(
        record.log_record
        for record in log_exporter.get_finished_logs()
        if json.loads(record.log_record.body).get("message") == "simulated_failure"
    )
    assert failure_log.trace_id == failure_span.context.trace_id
    assert failure_log.attributes["simulation"] == "http_503"
    assert failure_log.attributes["status"] == 503
    assert json.loads(failure_log.body)["trace_id"] == format(
        failure_span.context.trace_id, "032x"
    )
    app.extensions["telemetry"].shutdown()


def test_request_metrics_include_requests_errors_latency_and_health():
    """In-memory collection sees counts, 5xx errors, latency, and health."""
    reader = InMemoryMetricReader()
    app = create_app(
        telemetry_enabled=True,
        metric_reader=reader,
        span_exporter=InMemorySpanExporter(),
        log_exporter=InMemoryLogExporter(),
    )
    def service_unavailable():
        """Return a server error to exercise the 5xx counter."""
        return "unavailable", 503

    app.add_url_rule("/test-error", view_func=service_unavailable)

    client = app.test_client()
    client.get("/")
    client.get("/test-error")

    metrics_data = reader.get_metrics_data()
    metrics = {
        metric.name: metric
        for resource_metrics in metrics_data.resource_metrics
        for scope_metrics in resource_metrics.scope_metrics
        for metric in scope_metrics.metrics
    }
    assert metrics["http.server.request.count"].data.data_points
    assert metrics["http.server.request.duration"].data.data_points
    error_points = metrics["http.server.request.error_count"].data.data_points
    assert sum(point.value for point in error_points) == 1
    assert metrics["app.health"].data.data_points[0].value == 1
    app.extensions["telemetry"].shutdown()


def test_requests_create_correlated_server_spans():
    """OTLP traces and logs share the server span's trace ID."""
    exporter = InMemorySpanExporter()
    log_exporter = InMemoryLogExporter()
    app = create_app(
        telemetry_enabled=True,
        metric_reader=InMemoryMetricReader(),
        span_exporter=exporter,
        log_exporter=log_exporter,
    )

    response = app.test_client().get("/")

    app.extensions["telemetry"].logger_provider.force_flush()
    spans = exporter.get_finished_spans()
    logs = log_exporter.get_finished_logs()
    assert response.status_code == 200
    assert len(spans) == 1
    assert spans[0].name == "GET /"
    assert spans[0].attributes["http.response.status_code"] == 200
    request_log = next(
        record.log_record
        for record in logs
        if json.loads(record.log_record.body).get("message") == "request"
    )
    assert request_log.trace_id == spans[0].context.trace_id
    app.extensions["telemetry"].shutdown()


def test_python_library_logs_are_exported_as_json_with_fields():
    """Propagated Python logs reach OTLP with JSON keys and trace context."""
    exporter = InMemorySpanExporter()
    log_exporter = InMemoryLogExporter()
    app = create_app(
        telemetry_enabled=True,
        metric_reader=InMemoryMetricReader(),
        span_exporter=exporter,
        log_exporter=log_exporter,
    )
    library_logger = logging.getLogger("sample.library")

    def emit_library_log():
        """Emit a representative non-Flask Python log record."""
        library_logger.warning(
            "background_task_failed",
            extra={"task_id": "task-42", "failure_kind": "timeout"},
        )
        return "logged", 200

    app.add_url_rule("/test-library-log", view_func=emit_library_log)
    response = app.test_client().get("/test-library-log")
    app.extensions["telemetry"].logger_provider.force_flush()

    assert response.status_code == 200
    log_record = next(
        record.log_record
        for record in log_exporter.get_finished_logs()
        if record.log_record.attributes.get("task_id") == "task-42"
    )
    json_fields = json.loads(log_record.body)
    assert json_fields["message"] == "background_task_failed"
    assert json_fields["task_id"] == "task-42"
    assert json_fields["failure_kind"] == "timeout"
    assert log_record.attributes["failure_kind"] == "timeout"
    assert log_record.trace_id == next(
        span.context.trace_id for span in exporter.get_finished_spans()
    )
    app.extensions["telemetry"].shutdown()


def test_telemetry_disabled_still_serves_requests_and_logs_trace_context():
    """Disabling exporters preserves endpoint responses and local correlation."""
    app = create_app(telemetry_enabled=False)
    logs = _capture_json_logs(app, "get", "/")

    assert app.test_client().get("/").status_code == 200
    record = next(record for record in logs if record["message"] == "request")
    assert record["trace_id"] != "0" * 32
    assert len(record["trace_id"]) == 32
    assert len(record["span_id"]) == 16


def test_export_failures_do_not_fail_application_requests():
    """Failed log/trace exporters cannot make an HTTP request fail."""
    class _UnavailableTraceExporter:
        def export(self, spans):
            """Report a failed export without raising into Flask."""
            return SpanExportResult.FAILURE

        def shutdown(self):
            """Provide the exporter lifecycle hook used by the SDK."""
            pass

    class _UnavailableLogExporter:
        def export(self, logs):
            """Report a failed export without raising into Flask."""
            return LogExportResult.FAILURE

        def shutdown(self):
            """Provide the exporter lifecycle hook used by the SDK."""
            pass

    app = create_app(
        telemetry_enabled=True,
        metric_reader=InMemoryMetricReader(),
        span_exporter=_UnavailableTraceExporter(),
        log_exporter=_UnavailableLogExporter(),
    )

    response = app.test_client().get("/")

    assert response.status_code == 200
    app.extensions["telemetry"].logger_provider.force_flush()
    app.extensions["telemetry"].shutdown()
