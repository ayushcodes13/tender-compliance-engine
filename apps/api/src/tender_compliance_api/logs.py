"""Structured, privacy-safe logging for Tender Compliance Engine (CP46).

Key invariants:
- Every log line is JSON-structured for easy aggregation.
- A per-request correlation ID is injected as a logging context variable
  so all log calls within a request share the same ID — including
  background jobs that pick up a queued task.
- No confidential document bodies or full prompt text are ever logged.
- Allowed log fields: IDs (org, project, document, version, actor), stage,
  status, latency_ms, provider/model, token counts, error category,
  retry count.  See ``_PRIVACY_UNSAFE_FIELDS`` below.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
import uuid
from datetime import UTC, datetime
from typing import Any

# Fields that must NEVER appear in a log line (privacy guardrail).
_PRIVACY_UNSAFE_FIELDS = frozenset(
    {
        "document_body",
        "raw_source",
        "full_text",
        "extracted_text",
        "cleaned_text",
        "source_text",
        "file_contents",
        "pdf_text",
        "user_text",
        "system_prompt",
        "api_key",
        "secret_key",
        "password",
        "token",
        "sha256",
        "checksum",
    }
)

_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)


def set_correlation_id(cid: str | None = None) -> str:
    """Set the current correlation ID, generating one if not provided."""
    cid = cid or uuid.uuid4().hex[:16]
    _correlation_id.set(cid)
    return cid


def get_correlation_id() -> str | None:
    """Return the current correlation ID, if set."""
    return _correlation_id.get()


class StructuredJsonFormatter(logging.Formatter):
    """Format log records as one JSON object per line.

    Includes the correlation ID (if set) and any extra fields from the
    log call, while filtering out privacy-unsafe keys.
    """

    def format(self, record: logging.LogRecord) -> str:
        # Build the payload from standard fields first.
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": get_correlation_id(),
        }

        # Merge extra fields attached by the caller (record.__dict__).
        extra_fields: dict[str, Any] = getattr(record, "extra_fields", {})
        for key, value in extra_fields.items():
            if key in _PRIVACY_UNSAFE_FIELDS:
                continue
            payload[key] = value

        # Attach exception info if present.
        if record.exc_info and record.exc_info[1] is not None:
            payload["error_type"] = type(record.exc_info[1]).__name__
            # Use a stable category, not the full message (which may
            # contain confidential data).
            payload["error_category"] = _categorize_error(
                record.exc_info[1]
            )

        return json.dumps(payload, default=str, ensure_ascii=False)


def _categorize_error(exc: BaseException) -> str:
    """Map exception types to stable, non-sensitive category strings.

    Raw exception messages are NOT logged — only the category.  This
    follows the Bynd telemetry SOP: error category is allowed,
    raw exception message is not.
    """
    name = type(exc).__name__
    if "Timeout" in name:
        return "timeout"
    if "RateLimit" in name or "quota" in name.lower():
        return "rate_limit"
    if "Auth" in name:
        return "auth_error"
    if "NotFound" in name or "Not Found" in name:
        return "not_found"
    if "Validation" in name:
        return "validation_error"
    if "Conflict" in name:
        return "conflict"
    if "Connection" in name:
        return "connection_error"
    return "runtime_error"


def get_logger(name: str) -> logging.Logger:
    """Return a logger pre-configured with the structured JSON handler."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(StructuredJsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def log_event(
    logger: logging.Logger,
    level: int,
    message: str,
    *,
    correlation_id: str | None = None,
    **fields: Any,
) -> None:
    """Emit a structured log event with safe extra fields.

    Filters out any privacy-unsafe field keys.
    """
    safe_fields: dict[str, Any] = {}
    for key, value in fields.items():
        if key in _PRIVACY_UNSAFE_FIELDS:
            logger.warning(
                "Refusing to log privacy-unsafe field: %s", key
            )
            continue
        safe_fields[key] = value

    if correlation_id:
        _correlation_id.set(correlation_id)

    logger.log(
        level,
        message,
        extra={"extra_fields": safe_fields},
    )
