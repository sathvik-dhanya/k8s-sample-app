import json
import logging

from app.main import create_app


def _capture_json_logs(app, method: str, path: str) -> list[dict]:
    """Make a test request and return any JSON log records emitted."""
    records: list[dict] = []

    class _Capture(logging.Handler):
        def emit(self, record):
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
    app = create_app()
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["service"] == "python-app"
    assert "Hello" in payload["message"]


def test_access_log_is_valid_json():
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
    app = create_app()
    logs = _capture_json_logs(app, "get", "/healthz/live")

    record = logs[-1]
    assert record["path"] == "/healthz/live"
    assert record["status"] == 200


def test_liveness_endpoint():
    app = create_app()
    client = app.test_client()

    response = client.get("/healthz/live")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "alive"
    assert payload["probe"] == "liveness"


def test_readiness_log_contains_probe_path():
    app = create_app()
    logs = _capture_json_logs(app, "get", "/healthz/ready")

    record = logs[-1]
    assert record["path"] == "/healthz/ready"
    assert record["status"] == 200


def test_readiness_endpoint():
    app = create_app()
    client = app.test_client()

    response = client.get("/healthz/ready")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ready"
    assert payload["probe"] == "readiness"
