"""
Structured JSON logging with PII scrubbing.

Sensitive field values (passwords, tokens, emails) are redacted
before any log record is serialised to stdout.
"""
import json
import logging
import re
import traceback as tb

_SENSITIVE_KEYS = frozenset({
    "password", "password1", "password2",
    "token", "access", "refresh",
    "access_token", "refresh_token",
    "authorization", "secret", "hmac_secret",
    "credit_card", "card_number",
})

_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9.\-]+")


def _scrub(value: object) -> object:
    """Recursively redact sensitive data from dicts, lists, and strings."""
    if isinstance(value, dict):
        return {
            k: "***REDACTED***" if k.lower() in _SENSITIVE_KEYS else _scrub(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    if isinstance(value, str):
        return _EMAIL_RE.sub("***@***.***", value)
    return value


class PiiScrubbingJsonFormatter(logging.Formatter):
    """Emit each log record as a single PII-scrubbed JSON line."""

    _SKIP = frozenset({
        "msg", "args", "levelname", "levelno", "pathname",
        "filename", "module", "exc_info", "exc_text", "stack_info",
        "lineno", "funcName", "created", "msecs", "relativeCreated",
        "thread", "threadName", "processName", "process", "name",
        "message",
    })

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        payload: dict = {
            "level": record.levelname,
            "logger": record.name,
            "message": _scrub(record.message),
            "time": self.formatTime(record, self.datefmt),
        }
        # Attach any extra fields, scrubbed
        for key, val in record.__dict__.items():
            if key not in self._SKIP and not key.startswith("_"):
                payload[key] = _scrub(val)
        if record.exc_info:
            payload["exc"] = tb.format_exception(*record.exc_info)
        return json.dumps(payload, default=str)
