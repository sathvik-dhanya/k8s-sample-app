"""Configure root and Flask app loggers to emit JSON."""

import logging
import sys

from pythonjsonlogger.json import JsonFormatter

LOG_LEVEL = logging.INFO
_JSON_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_json_logging(app_logger: logging.Logger) -> None:
    """Replace all handlers on *app_logger* with a JSON stdout handler."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(_JSON_FORMAT))

    # Replace any default handlers Flask installed
    app_logger.handlers.clear()
    app_logger.addHandler(handler)
    app_logger.setLevel(LOG_LEVEL)
    # Prevent log records from bubbling to the root logger's plain handler
    app_logger.propagate = False
