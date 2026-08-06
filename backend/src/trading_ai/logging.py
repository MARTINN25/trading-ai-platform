"""Minimal structured JSON logging (ADR-0009).

Emits one JSON object per log line with the minimal required fields
(timestamp in UTC, level, component, logger name, message). Does not
log request bodies, headers, or any secret values.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

_COMPONENT = "backend"


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "component": _COMPONENT,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            payload["error_type"] = record.exc_info[0].__name__
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
