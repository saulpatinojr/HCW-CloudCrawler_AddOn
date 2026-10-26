"""Redaction for the log path only. Responses carry the visitor's own data back to them; logs never do.

The rules live in the engine (`cloud_crawler_core.redaction`, adopted from the App unchanged, ADR 0001). This module
re-exports what the lab uses and adds the one thing the engine cannot know: the few words only the lab writes to its
logs (its human-verification outcomes, its session events and its upload format names). Those words are checked here;
every other value goes through the engine's own guard, so a change to the engine's rules reaches the lab with the next
engine release and nothing is copied.
"""

from __future__ import annotations

from typing import Any

from cloud_crawler_core.redaction import ALLOWED_WORDS as ENGINE_ALLOWED_WORDS
from cloud_crawler_core.redaction import VisitorDataError, scrub
from cloud_crawler_core.redaction import assert_no_visitor_data as _engine_assert_no_visitor_data

# Words that only this edition logs. They are fixed event names, outcome codes and format names, never visitor data.
LAB_ONLY_WORDS: frozenset[str] = frozenset(
    {
        "session_opened",
        "session_closed",
        "turnstile_verified",
        "turnstile_rejected",
        "turnstile_disabled",
        "turnstile_failed",
        "turnstile_not_configured",
        "unsupported_media_type",
        "arg-json",
        "arg-csv",
    }
)

ALLOWED_WORDS: frozenset[str] = ENGINE_ALLOWED_WORDS | LAB_ONLY_WORDS

__all__ = [
    "ALLOWED_WORDS",
    "ENGINE_ALLOWED_WORDS",
    "LAB_ONLY_WORDS",
    "VisitorDataError",
    "assert_no_visitor_data",
    "scrub",
]


def assert_no_visitor_data(event: dict[str, Any]) -> None:
    """The single guard before the log writer. The engine's check, with this edition's own words also allowed."""
    _engine_assert_no_visitor_data(
        {key: (None if isinstance(value, str) and value in LAB_ONLY_WORDS else value) for key, value in event.items()}
    )
