"""Redaction for the log path only. Responses carry the visitor's own data back to them; logs never do.

This module is a copy of the engine's `cloud_crawler_core.redaction`, carried here only until the engine is adopted
from the App (ADR 0001). When `cloud-crawler-core` becomes a dependency this file is deleted and the two imports in
`security/logging.py` and `__main__.py` point at the engine's module; the two must stay identical until then.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

_GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_SUBSCRIPTION_PATH = re.compile(r"/subscriptions/[^\s\"']*", re.IGNORECASE)
_SECRET_SHAPED = re.compile(
    r"(AccountKey=[A-Za-z0-9+/=]{20,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}|sig=[A-Za-z0-9%+/=]{20,}|ghp_[A-Za-z0-9]{20,})"
)

ALLOWED_WORDS: frozenset[str] = frozenset(
    {
        # event names
        "startup",
        "shutdown",
        "session_opened",
        "session_closed",
        "evidence_ingested",
        "evidence_rejected",
        "drift_evaluated",
        "turnstile_verified",
        "turnstile_rejected",
        "turnstile_disabled",
        "rate_limited",
        "overloaded",
        "sweep",
        "request_error",
        "unhandled_error",
        # formats, editions, states, codes
        "arg-json",
        "arg-csv",
        "azqr-report",
        "tf-state",
        "tf-plan",
        "lab",
        "ok",
        "error",
        "invalid_json",
        "invalid_request",
        "turnstile_failed",
        "turnstile_not_configured",
        "too_large",
        "unsupported_media_type",
        "ingestion_failed",
        "too_many_rows",
        "not_found",
        "method_not_allowed",
        "internal_error",
        "warning",
        "true",
        "false",
    }
)


class VisitorDataError(ValueError):
    """Raised when a log event would carry anything other than counts, durations and known words."""


def scrub(text: str) -> str:
    """Replace GUIDs, subscription paths and secret-shaped strings. Used on exception text before it is logged."""
    text = _SECRET_SHAPED.sub("<redacted>", text)
    text = _SUBSCRIPTION_PATH.sub("<redacted>", text)
    text = _GUID.sub("<redacted>", text)
    return text[:500]


def assert_no_visitor_data(event: dict[str, Any]) -> None:
    """The single guard before the log writer: every value is numeric, boolean, None, an Enum, or an allowed word."""
    for key, value in event.items():
        if not isinstance(key, str) or not key.isidentifier():
            raise VisitorDataError("log keys must be identifiers")
        if value is None or isinstance(value, bool | int | float | Enum):
            continue
        if isinstance(value, str) and value in ALLOWED_WORDS:
            continue
        raise VisitorDataError(f"log field {key!r} is not a count, flag or allowed word")
