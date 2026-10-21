"""JSON lines to stderr through one guarded writer. Counts, durations, flags and allowed words only."""

from __future__ import annotations

import json
import sys
import time
from typing import Any

from cloud_crawler_lab.security.redaction import assert_no_visitor_data, scrub

_silent = False


def configure(*, silent: bool) -> None:
    global _silent
    _silent = silent


def _write(event: dict[str, Any]) -> None:
    scrubbed = event.pop("scrubbed", None)
    assert_no_visitor_data(event)
    if scrubbed is not None:
        event["scrubbed"] = scrub(str(scrubbed))
    if _silent:
        return
    sys.stderr.write(json.dumps(event, separators=(",", ":"), default=str) + "\n")
    sys.stderr.flush()


def log_event(event: str, **fields: Any) -> None:
    _write({"ts": round(time.time(), 3), "event": event, **fields})


def log_exception(event: str, exc: BaseException, **fields: Any) -> None:
    _write(
        {
            "ts": round(time.time(), 3),
            "event": event,
            "error": True,
            **fields,
            "scrubbed": f"{type(exc).__name__}: {exc}",
        }
    )
