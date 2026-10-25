import json
import logging
import sys
from datetime import UTC, datetime

# Fields that must never reach logs, even if passed via `extra`.
_REDACT = {"password", "token", "access_token", "authorization", "merchant", "description", "amount_minor_units"}


class JsonFormatter(logging.Formatter):
    """One JSON object per line. Only whitelisted, non-sensitive context is emitted."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in ("request_id", "method", "path", "status", "duration_ms", "user_id", "event"):
            value = getattr(record, key, None)
            if value is not None and key not in _REDACT:
                payload[key] = value
        if record.exc_info:
            payload["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
        return json.dumps(payload, default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # Avoid uvicorn's access log, which would duplicate our request log line.
    logging.getLogger("uvicorn.access").disabled = True
