"""Structured (JSON) logging setup.

Previously nothing in this project configured logging at all -- the
connector sync path (`engine/connector_worker.py`,
`engine/sync_scheduler.py`) is the one piece of this app meant to run
unattended (a cron job / scheduled task pulling billing exports), and it
had no logs: a failed sync left no operational trail beyond whatever made
it into the database's own job-status column. `docs/ROADMAP.md` Phase 3
calls this out explicitly ("no logging framework is wired in").

`configure_logging()` sets up a root handler that emits one JSON object per
line (drop-in friendly for CloudWatch/Stackdriver/any log-shipping agent
that expects JSON) when `LOG_FORMAT=json` (the production default below),
or a readable plain-text format for local development
(`LOG_FORMAT=text`, or when running in a TTY without the env var set).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # Anything passed via logger.info(..., extra={...}) rides along.
        for key, value in record.__dict__.items():
            if key in _RESERVED_LOG_RECORD_ATTRS:
                continue
            payload.setdefault(key, value)
        return json.dumps(payload, default=str)


_RESERVED_LOG_RECORD_ATTRS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "taskName",
}

_configured = False


def configure_logging(level: str | None = None) -> None:
    """Idempotent: safe to call from multiple entry points (app.py, main.py, scripts)."""
    global _configured
    if _configured:
        return
    _configured = True

    log_level = getattr(logging, (level or os.getenv("LOG_LEVEL", "INFO")).upper(), logging.INFO)
    log_format = os.getenv("LOG_FORMAT", "json" if not sys.stderr.isatty() else "text")

    handler = logging.StreamHandler(sys.stderr)
    if log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        ))

    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers.clear()
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
