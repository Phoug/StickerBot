"""JSON logs with request correlation and configured secret redaction."""
import json
import logging
import os
import traceback
from contextvars import ContextVar
from datetime import datetime, timezone

request_id = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    def __init__(self, secrets=()):
        super().__init__()
        self.secrets = tuple(value for value in secrets if value)

    def format(self, record):
        # Uvicorn access arguments include query strings, including submitted URLs.
        if record.name == "uvicorn.access" and isinstance(record.args, tuple) and len(record.args) == 5:
            args = list(record.args)
            args[2] = str(args[2]).split("?", 1)[0]
            record = logging.makeLogRecord({**record.__dict__, "args": tuple(args)})
        payload = {
            "time": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "version": os.getenv("APP_VERSION", "dev"),
        }
        if identifier := request_id.get():
            payload["request_id"] = identifier
        for key in ("method", "route", "status", "duration_ms", "event"):
            if key in record.__dict__:
                payload[key] = record.__dict__[key]
        if record.exc_info:
            payload["exception"] = "".join(traceback.format_exception(*record.exc_info))
        for key, value in payload.items():
            if isinstance(value, str):
                for secret in self.secrets:
                    value = value.replace(secret, "[redacted]")
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(*secrets):
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(logging.StreamHandler())
    root.setLevel(logging.INFO)
    for handler in root.handlers:
        handler.setFormatter(JsonFormatter(secrets))
