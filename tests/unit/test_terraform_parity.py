"""A Terraform upload is accepted with the same limits, the same human check and the same content-free logs as an Azure
Resource Graph export (issue 29, "Done when", second box).

The route in `routes/uploads.py` does not look at the evidence kind before it rate-limits, checks the declared length,
verifies the visitor and streams the body in, so the properties hold by construction; these tests hold them per kind
anyway, so a future route that reads the kind early (or a per-kind fast path) cannot quietly skip one of them.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from cloud_crawler_lab.app import create_app
from cloud_crawler_lab.config import TURNSTILE_ACTION
from cloud_crawler_lab.routes import uploads
from cloud_crawler_lab.security import logging as logs

from ..conftest import JSON, make_body, make_settings
from ..terraform_documents import sample_plan, sample_state
from .test_upload_api import siteverify

TERRAFORM = [
    pytest.param("tf-state", sample_state, id="state"),
    pytest.param("tf-plan", sample_plan, id="plan"),
]
GOOD = {"good": {"success": True, "action": TURNSTILE_ACTION}}


def terraform_body(kind: str, document) -> dict:
    return make_body(kind=kind, content=document(), name="terraform.json")


@pytest.mark.parametrize(("kind", "document"), TERRAFORM)
def test_a_terraform_upload_fails_closed_without_human_verification_and_parses_nothing(monkeypatch, kind, document):
    monkeypatch.setattr(uploads, "process_upload", lambda *a, **k: pytest.fail("the body was parsed"))
    monkeypatch.setattr(uploads, "read_body", lambda *a, **k: pytest.fail("the body was read"))
    with TestClient(create_app(make_settings(allow_no_turnstile=False))) as c:
        r = c.post("/api/uploads", json=terraform_body(kind, document))
        assert r.status_code == 503 and r.json()["error"]["code"] == "turnstile_not_configured"


@pytest.mark.parametrize(("kind", "document"), TERRAFORM)
def test_a_terraform_upload_is_refused_on_a_bad_token_and_accepted_on_a_good_one(kind, document):
    seen: list = []
    app = create_app(
        make_settings(turnstile_secret="the-secret", rate_limit_posts=100), verifier=siteverify(GOOD, seen)
    )
    with TestClient(app) as c:
        body = terraform_body(kind, document)
        for headers in ({}, {"x-turnstile-token": "bad"}):
            r = c.post("/api/uploads", json=body, headers=headers)
            assert r.status_code == 403 and r.json()["error"]["code"] == "turnstile_failed", headers
        r = c.post("/api/uploads", json=body, headers={"x-turnstile-token": "good"})
        assert r.status_code == 201, r.text[:300]
        [evidence] = r.json()["evidence"]
        assert evidence["kind"] == kind and evidence["readByDetectors"] is True and evidence["resourceCount"] > 0
        assert "the-secret" not in r.text
    # a missing token is refused before the verifier is asked; the bad and the good token both reach it
    assert [call["form"]["response"] for call in seen] == ["bad", "good"]


@pytest.mark.parametrize(("kind", "document"), TERRAFORM)
def test_a_terraform_upload_over_the_size_limit_is_refused_before_verification_is_spent(kind, document):
    seen: list = []
    raw = json.dumps(terraform_body(kind, document)).encode()
    app = create_app(
        make_settings(turnstile_secret="the-secret", max_upload_bytes=len(raw) - 1), verifier=siteverify(GOOD, seen)
    )
    with TestClient(app) as c:
        r = c.post("/api/uploads", content=raw, headers=JSON | {"x-turnstile-token": "good"})
        assert r.status_code == 413 and r.json()["error"]["code"] == "too_large"
        assert r.json()["error"]["details"] == {"maxUploadBytes": len(raw) - 1}
    assert seen == [], "the declared length is checked before the visitor's verification is used up"


@pytest.mark.parametrize(("kind", "document"), TERRAFORM)
def test_a_terraform_upload_counts_against_the_same_row_limit(kind, document):
    entries = len(document()["resources" if kind == "tf-state" else "resource_changes"])
    with TestClient(create_app(make_settings(max_rows=entries - 1))) as c:
        r = c.post("/api/uploads", json=terraform_body(kind, document))
        assert r.status_code == 422 and r.json()["error"]["code"] == "too_many_rows"
        assert r.json()["error"]["details"] == {"evidenceIndex": 0, "maxRows": entries - 1}
    with TestClient(create_app(make_settings(max_rows=entries))) as c:
        assert c.post("/api/uploads", json=terraform_body(kind, document)).status_code == 201


@pytest.mark.parametrize(("kind", "document"), TERRAFORM)
def test_an_accepted_terraform_upload_logs_counts_and_fixed_words_only(monkeypatch, kind, document):
    import io
    import sys

    buffer = io.StringIO()
    monkeypatch.setattr(sys, "stderr", buffer)
    body = terraform_body(kind, document)
    with TestClient(create_app(make_settings(log_silent=False, rate_limit_posts=100))) as c:
        r = c.post("/api/uploads", json=body)
        assert r.status_code == 201, r.text[:300]
    logs.configure(silent=True)
    lines = [json.loads(line) for line in buffer.getvalue().splitlines() if line.startswith("{")]
    opened = next(line for line in lines if line["event"] == "session_opened")
    assert all(isinstance(value, int | float | bool) or key == "event" for key, value in opened.items())
    text = buffer.getvalue()
    for word in ("hcwsample", "azurerm_", "terraform.json", "resourceGroups", kind):
        assert word not in text, f"the log repeats {word!r} from the upload"
