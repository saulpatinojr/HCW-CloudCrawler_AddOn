import io
import json
import sys
import urllib.error

import pytest
from fastapi import Request

from cloud_crawler_lab.config import Settings
from cloud_crawler_lab.errors import ApiError
from cloud_crawler_lab.security import logging as logs
from cloud_crawler_lab.security.headers import cache_control_for, content_security_policy, security_headers
from cloud_crawler_lab.security.limits import client_address, read_body
from cloud_crawler_lab.security.ratelimit import MAX_TRACKED_CLIENTS, ConcurrencyBound, TokenBucketLimiter
from cloud_crawler_lab.security.redaction import VisitorDataError, scrub
from cloud_crawler_lab.security.turnstile import SITEVERIFY_URL, Verdict, verify


def _opener(payload, *, raise_exc=None, capture=None):
    def opener(request, timeout):
        assert request.full_url == SITEVERIFY_URL and timeout == 5.0
        if capture is not None:
            capture.append(request.data.decode())
        if raise_exc:
            raise raise_exc
        return json.dumps(payload).encode() if not isinstance(payload, bytes) else payload

    return opener


def test_turnstile_verdicts():
    assert verify("s", None, "1.2.3.4") == Verdict(False, ["missing-input-response"])
    assert verify("s", "x" * 3000, None).codes == ["missing-input-response"]
    sent = []
    assert verify(
        "s", "tok", "1.2.3.4", opener=_opener({"success": True, "action": "cloud-crawler-upload"}, capture=sent)
    ).ok
    assert "remoteip=1.2.3.4" in sent[0] and "secret=s" in sent[0] and "response=tok" in sent[0]
    assert verify("s", "tok", None, opener=_opener({"success": True, "action": "other"})).codes == ["action-mismatch"]
    assert verify(
        "s", "tok", None, opener=_opener({"success": False, "error-codes": ["timeout-or-duplicate", 5]})
    ).codes == ["timeout-or-duplicate"]
    assert verify("s", "tok", None, opener=_opener({"success": False})).codes == ["invalid-input-response"]
    assert verify("s", "tok", None, opener=_opener(b"not json")).codes == ["verification-unavailable"]
    assert verify("s", "tok", None, opener=_opener([1])).codes == ["verification-unavailable"]
    assert verify("s", "tok", None, opener=_opener({}, raise_exc=urllib.error.URLError("x"))).codes == [
        "verification-unavailable"
    ]
    assert verify("s", "tok", None, opener=_opener({}, raise_exc=TimeoutError())).codes == ["verification-unavailable"]


def test_csp_and_headers_follow_settings():
    plain = Settings()
    csp = content_security_policy(plain)
    assert (
        "frame-ancestors 'none'" in csp
        and "challenges.cloudflare.com" not in csp
        and "base-uri 'none'" in csp
        and "form-action 'self'" in csp
    )
    headers = dict(security_headers(plain))
    assert (
        headers[b"x-frame-options"] == b"DENY"
        and headers[b"x-addon-id"] == b"cloud-crawler"
        and headers[b"x-content-type-options"] == b"nosniff"
    )
    assert (
        headers[b"referrer-policy"] == b"no-referrer"
        and headers[b"permissions-policy"] == b"camera=(), microphone=(), geolocation=()"
    )
    framed = Settings(
        frame_ancestors="https://hybridcloudworks.com https://www.hybridcloudworks.com", turnstile_site_key="k"
    )
    csp = content_security_policy(framed)
    assert "frame-ancestors https://hybridcloudworks.com https://www.hybridcloudworks.com" in csp
    assert (
        "script-src 'self' https://challenges.cloudflare.com" in csp
        and "frame-src https://challenges.cloudflare.com" in csp
    )
    assert b"x-frame-options" not in dict(security_headers(framed))
    assert (
        cache_control_for("/api/health") == b"no-store"
        and cache_control_for("/") == b"no-cache"
        and cache_control_for("/app.js") == b"public, max-age=300"
    )


def test_token_bucket_refills_and_prunes():
    now = [0.0]
    limiter = TokenBucketLimiter(2, 10.0, clock=lambda: now[0])
    assert limiter.acquire("a") == (True, 0) and limiter.acquire("a") == (True, 0)
    allowed, retry = limiter.acquire("a")
    assert not allowed and retry >= 1
    assert limiter.acquire("b") == (True, 0), "clients are independent"
    now[0] += 5.0
    assert limiter.acquire("a") == (True, 0)
    limiter._buckets.clear()
    for i in range(MAX_TRACKED_CLIENTS):
        limiter.acquire(f"c{i}")
    now[0] += 100.0
    assert limiter.acquire("new") == (True, 0)
    assert len(limiter._buckets) < MAX_TRACKED_CLIENTS


def test_token_bucket_prune_clears_when_everyone_is_active():
    now = [0.0]
    limiter = TokenBucketLimiter(1, 1000.0, clock=lambda: now[0])
    for i in range(MAX_TRACKED_CLIENTS):
        limiter.acquire(f"c{i}")
    assert limiter.acquire("new") == (True, 0)
    assert len(limiter._buckets) == 1


@pytest.mark.anyio
async def test_concurrency_bound_times_out():
    bound = ConcurrencyBound(1, wait_seconds=0.05)
    assert await bound.acquire()
    assert not await bound.acquire()
    bound.release()
    assert await bound.acquire()
    bound.release()


def _request(headers: dict[str, str], chunks: list[bytes], client=("1.2.3.4", 1234)) -> Request:
    queue = [{"type": "http.request", "body": c, "more_body": True} for c in chunks]
    queue.append({"type": "http.request", "body": b"", "more_body": False})

    async def receive():
        return queue.pop(0)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/x",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": client,
        "query_string": b"",
    }
    return Request(scope, receive)


@pytest.mark.anyio
async def test_read_body_caps_declared_and_streamed_sizes():
    assert await read_body(_request({}, [b"ab", b"cd"]), 10) == b"abcd"
    with pytest.raises(ApiError) as declared:
        await read_body(_request({"content-length": "11"}, [b"x"]), 10)
    assert declared.value.status == 413 and declared.value.details == {"maxUploadBytes": 10}
    with pytest.raises(ApiError) as streamed:
        await read_body(_request({}, [b"x" * 6, b"y" * 6]), 10)
    assert streamed.value.status == 413


def test_client_address_trusts_the_proxy_only_when_told():
    direct = _request({"x-forwarded-for": "9.9.9.9, 8.8.8.8"}, [])
    assert client_address(direct, trust_proxy=False) == "1.2.3.4"
    assert client_address(direct, trust_proxy=True) == "9.9.9.9"
    assert client_address(_request({"x-forwarded-for": ""}, []), trust_proxy=True) == "1.2.3.4"
    assert client_address(_request({}, [], client=None), trust_proxy=False) == "unknown"


def test_scrub_replaces_identifiers_and_secret_shapes():
    out = scrub("key AccountKey=" + "A" * 40 + " at /subscriptions/00000000-0000-0000-0000-000000000001/rg x")
    assert "AccountKey" not in out and "00000000-0000" not in out and out.count("<redacted>") == 2
    assert len(scrub("z" * 1000)) == 500


def test_logging_writer_is_guarded(monkeypatch):
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stderr", buf)
    logs.configure(silent=False)
    logs.log_event("startup", n=1, flag=True)
    with pytest.raises(VisitorDataError):
        logs.log_event("startup", name="hcw-sample-aks")
    logs.log_exception("unhandled_error", RuntimeError("sub /subscriptions/00000000-0000-0000-0000-000000000001/x"))
    out = buf.getvalue()
    assert '"event":"startup"' in out and "00000000-0000" not in out and "<redacted>" in out
    logs.configure(silent=True)
    logs.log_event("startup")
    assert out == buf.getvalue()
