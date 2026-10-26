"""Three properties of the upload gate that mutation checks showed nothing was holding: an upload that
declares it is too large does not spend the visitor's single-use verification; every refusal the route can
raise is a word the log knows; an owner token longer than the header allows is not looked up."""

import json
import re

from fastapi import Request
from fastapi.testclient import TestClient

from cloud_crawler_lab.app import create_app
from cloud_crawler_lab.errors import ApiError
from cloud_crawler_lab.routes import uploads
from cloud_crawler_lab.security.redaction import ALLOWED_WORDS

from ..conftest import JSON, ROOT, make_body, make_settings
from ..unit.test_upload_api import GOOD, siteverify


def test_an_upload_that_declares_it_is_too_large_does_not_spend_the_visitors_verification():
    seen: list = []
    body = json.dumps(make_body()).encode()
    app = create_app(
        make_settings(turnstile_secret="the-secret", max_upload_bytes=len(body) - 1), verifier=siteverify(GOOD, seen)
    )
    with TestClient(app) as c:
        r = c.post("/api/uploads", content=body, headers=JSON | {"x-turnstile-token": "good"})
        assert r.status_code == 413 and r.json()["error"]["code"] == "too_large"
        assert seen == [], "refused by its declared size before the verification service was asked"
    app = create_app(
        make_settings(turnstile_secret="the-secret", max_upload_bytes=len(body)), verifier=siteverify(GOOD, seen)
    )
    with TestClient(app) as c:
        r = c.post("/api/uploads", content=body, headers=JSON | {"x-turnstile-token": "good"})
        assert r.status_code == 201 and len(seen) == 1, "the same upload within the limit is verified once and accepted"


def test_every_refusal_the_application_can_raise_is_a_word_the_log_knows():
    raised = set()
    for path in (ROOT / "src" / "cloud_crawler_lab").rglob("*.py"):
        raised |= set(re.findall(r'ApiError\(\s*\d{3},\s*"([a-z_]+)"', path.read_text(encoding="utf-8")))
    assert raised, "the scan found no refusals at all"
    unknown = sorted(code for code in raised if code not in ALLOWED_WORDS)
    assert unknown == [], f"refusals the log would have to call just 'error': {unknown}"


def test_a_refusal_whose_code_the_log_does_not_know_is_logged_as_error_not_by_its_code():
    assert uploads._code(ApiError(422, "too_complex", "m")) == "too_complex"
    assert uploads._code(ApiError(418, "a code that is not a log word", "m")) == "error"


def _request(token: str) -> Request:
    scope = {"type": "http", "method": "GET", "path": "/x", "headers": [(b"x-owner-token", token.encode())]}
    return Request(scope)


def test_an_owner_token_the_header_could_not_carry_is_not_looked_up():
    assert uploads._owner_token(_request("t" * uploads.MAX_TOKEN_LENGTH)) == "t" * uploads.MAX_TOKEN_LENGTH
    assert uploads._owner_token(_request("t" * (uploads.MAX_TOKEN_LENGTH + 1))) is None
    assert uploads._owner_token(_request("   ")) is None and uploads._owner_token(_request("")) is None
    assert uploads._owner_token(_request("  padded  ")) == "padded"
