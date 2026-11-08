import logging
import os
import time

from flask import Flask, g, jsonify, request

from app.logging_config import configure_json_logging, configure_otel_logging
from app.telemetry import Telemetry


def create_app(
    *,
    telemetry_enabled: bool | None = None,
    simulation_enabled: bool | None = None,
    metric_reader=None,
    span_exporter=None,
    log_exporter=None,
) -> Flask:
    """Build the Flask app and optionally export its telemetry over OTLP."""
    app = Flask(__name__)

    if simulation_enabled is None:
        simulation_enabled = os.getenv("SIMULATION_ENABLED", "false").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    configure_json_logging(app.logger)
    logger = app.logger
    telemetry = Telemetry(
        enabled=telemetry_enabled,
        metric_reader=metric_reader,
        span_exporter=span_exporter,
        log_exporter=log_exporter,
    )
    app.extensions["telemetry"] = telemetry
    if telemetry.logging_handler is not None:
        configure_otel_logging(telemetry.logging_handler)
        # Capture propagated records from Flask, Werkzeug, and app libraries.
        logging.getLogger().addHandler(telemetry.logging_handler)
        logging.getLogger().setLevel(logging.INFO)

    @app.before_request
    def _start_timer():
        """Start request timing and the associated server span."""
        request._start_time = time.perf_counter()
        # Use a fixed fallback for unmatched URLs to avoid high-cardinality metrics.
        route = request.url_rule.rule if request.url_rule else "unmatched"
        g.otel_span_scope = telemetry.start_request(
            request.method, route, request.headers
        )
        g.otel_span = g.otel_span_scope.__enter__()

    @app.after_request
    def _log_request(response):
        """Record request metrics, correlate the JSON log, and close its span."""
        duration = time.perf_counter() - request._start_time
        duration_ms = round(duration * 1000, 2)
        route = request.url_rule.rule if request.url_rule else "unmatched"
        telemetry.record_request(
            request.method, route, response.status_code, duration
        )
        telemetry.finish_span(g.otel_span, response.status_code)
        logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
                "trace_id": format(
                    g.otel_span.get_span_context().trace_id, "032x"
                ),
            },
        )
        g.otel_span_scope.__exit__(None, None, None)
        return response

    # ── routes ────────────────────────────────────────────────────────────────
    @app.get("/")
    def index():
        """Return the sample welcome response."""
        return jsonify(
            {
                "message": "Hello from the Python app running on Kubernetes!",
                "service": "python-app",
            }
        )

    @app.get("/healthz/live")
    def liveness():
        """Report whether the Flask process is alive."""
        return jsonify({"status": "alive", "probe": "liveness"})

    @app.get("/healthz/ready")
    def readiness():
        """Report that the Flask app is ready to serve requests."""
        return jsonify({"status": "ready", "probe": "readiness"})

    if simulation_enabled:
        @app.get("/simulate/slow")
        def simulate_slow_request():
            """Add a short, fixed delay to demonstrate request latency metrics."""
            time.sleep(0.5)
            return jsonify({"simulation": "slow_request", "status": "complete"})

        @app.get("/simulate/error")
        def simulate_server_error():
            """Return a deliberate 503 and emit a trace-correlated error log."""
            logger.error(
                "simulated_failure",
                extra={
                    "simulation": "http_503",
                    "error": "Deliberate local observability demo failure",
                    "status": 503,
                },
            )
            return (
                jsonify(
                    {
                        "simulation": "http_503",
                        "error": "Deliberate local observability demo failure",
                    }
                ),
                503,
            )

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.logger.info("starting", extra={"port": port})
    app.run(host="0.0.0.0", port=port)
