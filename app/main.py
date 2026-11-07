import os
import time

from flask import Flask, jsonify, request

from app.logging_config import configure_json_logging


def create_app() -> Flask:
    app = Flask(__name__)

    configure_json_logging(app.logger)
    logger = app.logger

    # ── access log ────────────────────────────────────────────────────────────
    @app.before_request
    def _start_timer():
        request._start_time = time.perf_counter()

    @app.after_request
    def _log_request(response):
        duration_ms = round(
            (time.perf_counter() - request._start_time) * 1000, 2
        )
        logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response

    # ── routes ────────────────────────────────────────────────────────────────
    @app.get("/")
    def index():
        return jsonify(
            {
                "message": "Hello from the Python app running on Kubernetes!",
                "service": "python-app",
            }
        )

    @app.get("/healthz/live")
    def liveness():
        """Liveness probe – confirms the process is running."""
        return jsonify({"status": "alive", "probe": "liveness"})

    @app.get("/healthz/ready")
    def readiness():
        """Readiness probe – confirms the app is ready to serve traffic."""
        return jsonify({"status": "ready", "probe": "readiness"})

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.logger.info("starting", extra={"port": port})
    app.run(host="0.0.0.0", port=port)
