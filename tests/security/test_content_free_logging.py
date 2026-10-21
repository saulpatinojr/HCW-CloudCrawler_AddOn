"""Logs carry counts, durations, flags and allowed words only; never ids, names, tokens or cell content."""

import io
import json
import sys

from fastapi.testclient import TestClient

from cloud_crawler_lab.app import create_app
from cloud_crawler_lab.security import logging as logs
from cloud_crawler_lab.security.redaction import ALLOWED_WORDS

from ..conftest import make_settings


def test_lifecycle_logs_are_content_free(monkeypatch):
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stderr", buf)
    app = create_app(make_settings(log_silent=False, site_origins=("https://hybridcloudworks.com",)))
    with TestClient(app) as c:
        c.get("/api/health")
        c.get("/api/missing")
        c.get("/")
    lines = [json.loads(line) for line in buf.getvalue().splitlines()]
    events = [line["event"] for line in lines]
    assert events[0] == "startup" and events[-1] == "shutdown"
    text = buf.getvalue()
    assert "hybridcloudworks" not in text and "/api/" not in text and "index.html" not in text
    for line in lines:
        for key, value in line.items():
            if key in ("ts",):
                continue
            assert value is None or isinstance(value, bool | int | float) or value in ALLOWED_WORDS, (key, value)
    logs.configure(silent=True)


def test_turnstile_disabled_warning_is_logged_at_startup(monkeypatch):
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stderr", buf)
    app = create_app(make_settings(log_silent=False, allow_no_turnstile=True))
    with TestClient(app):
        pass
    assert any(
        json.loads(line) == {**json.loads(line), "event": "turnstile_disabled", "warning": True}
        for line in buf.getvalue().splitlines()
    )
    logs.configure(silent=True)
