import asyncio
import json
import threading
import time

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from cloud_crawler_lab import analysis
from cloud_crawler_lab import app as app_module
from cloud_crawler_lab.app import create_app
from cloud_crawler_lab.config import TURNSTILE_ACTION
from cloud_crawler_lab.routes import uploads
from cloud_crawler_lab.store import UploadStore

from ..conftest import JSON, load_sample, make_body, make_settings, one_claim_decision


def create(client, body=None, **kwargs):
    return client.post("/api/uploads", json=body if body is not None else make_body(), **kwargs)


def owner(created) -> dict:
    return {"x-owner-token": created.json()["ownerToken"]}


@pytest.fixture
def created(client):
    r = create(client)
    assert r.status_code == 201, r.text
    return r


def test_the_whole_lifecycle_create_read_files_delete(client, created):
    body = created.json()
    upload_id, headers = body["uploadId"], owner(created)
    assert set(body) == {
        "uploadId",
        "ownerToken",
        "expiresAt",
        "notice",
        "summary",
        "decision",
        "evidence",
        "claims",
        "listing",
        "proposalCount",
        "files",
    }
    assert body["expiresAt"].endswith("Z") and body["files"] == ["NOT-AN-AUDIT.md", "report.json", "report.md"]
    assert body["summary"] == {
        "supported": 3,
        "contradicted": 2,
        "unknown": 0,
        "notApplicable": 8,
        "score": 60.0,
        "coverage": 1.0,
    }
    assert body["decision"]["status"] == "draft" and body["decision"]["claimCount"] == 1
    assert body["proposalCount"] == 1 and body["evidence"][0]["resourceCount"] == 13

    detail = client.get(f"/api/uploads/{upload_id}", headers=headers)
    assert detail.status_code == 200
    full = detail.json()
    assert full["uploadId"] == upload_id and full["decision"]["status"] == "draft"
    assert full["decision"]["title"] == "Production data platform must be zone redundant"
    assert len(full["decision"]["claims"]) == 1 and full["engine"]["name"] == "cloud-crawler-core"
    assert [f["verdict"] for f in full["findings"]] == [
        "contradicted",
        "contradicted",
        "supported",
        "supported",
        "supported",
    ]
    assert len(full["contradictions"]) == 2
    [proposal] = full["proposals"]
    assert (
        proposal["kind"] == "contradiction"
        and proposal["status"] == "open"
        and len(proposal["impactedResourceIds"]) == 2
    )
    assert full["claims"][0]["contradicted"] == 2 and full["claims"][0]["notApplicable"] == 8
    assert full["listing"]["notApplicableNotListed"] == 8 and full["listing"]["findingsLeftOut"] == 0

    md = client.get(f"/api/uploads/{upload_id}/files/report.md", headers=headers)
    assert md.status_code == 200 and md.headers["content-type"].startswith("text/markdown")
    assert md.headers["content-disposition"] == 'attachment; filename="cloud-crawler-report.md"'
    assert "Production data platform must be zone redundant" in md.text and "What is listed" in md.text
    report = client.get(f"/api/uploads/{upload_id}/files/report.json", headers=headers)
    assert report.status_code == 200 and report.headers["content-type"] == "application/json"
    assert report.json()["lab"]["edition"] == "lab" and report.json()["decision"]["status"] == "draft"
    note = client.get(f"/api/uploads/{upload_id}/files/NOT-AN-AUDIT.md", headers=headers)
    assert note.status_code == 200 and note.text.startswith("# Not an audit")

    assert client.delete(f"/api/uploads/{upload_id}", headers=headers).json() == {"deleted": True}
    assert client.get(f"/api/uploads/{upload_id}", headers=headers).status_code == 404
    assert client.get(f"/api/uploads/{upload_id}/files/report.md", headers=headers).status_code == 404
    assert client.delete(f"/api/uploads/{upload_id}", headers=headers).status_code == 404


def test_every_output_carries_the_not_an_audit_note(client, created):
    upload_id, headers = created.json()["uploadId"], owner(created)
    assert "Not an audit" in created.json()["notice"]
    detail = client.get(f"/api/uploads/{upload_id}", headers=headers).json()
    assert detail["notAnAudit"]["file"] == "NOT-AN-AUDIT.md" and detail["notAnAudit"]["text"].startswith(
        "# Not an audit"
    )
    assert "Not an audit" in detail["notAnAudit"]["line"]
    md = client.get(f"/api/uploads/{upload_id}/files/report.md", headers=headers).text
    assert "Not an audit" in md and md.rstrip().endswith("what the verdicts do and do not mean.")
    report = client.get(f"/api/uploads/{upload_id}/files/report.json", headers=headers).json()
    assert "Not an audit" in report["lab"]["notAnAudit"]
    assert "NOT-AN-AUDIT.md" in detail["files"]


def test_the_results_are_never_cached(client, created):
    upload_id, headers = created.json()["uploadId"], owner(created)
    assert created.headers["cache-control"] == "no-store"
    for path in ("", "/files/report.md"):
        assert client.get(f"/api/uploads/{upload_id}{path}", headers=headers).headers["cache-control"] == "no-store"


def test_owner_token_isolation(client, created):
    upload_id = created.json()["uploadId"]
    other = create(client)
    for headers in ({}, {"x-owner-token": "wrong"}, {"x-owner-token": "x" * 200}, owner(other)):
        for path in ("", "/files/report.md", "/files/report.json", "/files/NOT-AN-AUDIT.md"):
            r = client.get(f"/api/uploads/{upload_id}{path}", headers=headers)
            assert r.status_code == 404 and r.json() == {"error": {"code": "not_found", "message": "Not found."}}
        assert client.delete(f"/api/uploads/{upload_id}", headers=headers).status_code == 404
    assert client.get("/api/uploads/00000000-0000-0000-0000-000000000099", headers=owner(created)).status_code == 404
    assert client.get(f"/api/uploads/{upload_id}", headers=owner(created)).status_code == 200


def test_the_token_is_in_the_creating_response_only(client, created):
    token = created.json()["ownerToken"]
    upload_id = created.json()["uploadId"]
    for path in ("", "/files/report.md", "/files/report.json"):
        assert token not in client.get(f"/api/uploads/{upload_id}{path}", headers=owner(created)).text


@pytest.mark.parametrize(
    "content_type",
    [
        "text/plain",
        "application/xml",
        "application/x-yaml",
        "application/zip",
        "multipart/form-data; boundary=x",
        "text/csv",
        "",
    ],
)
def test_only_json_is_accepted(client, content_type):
    headers = {"content-type": content_type} if content_type else {}
    r = client.post("/api/uploads", content=json.dumps(make_body()).encode(), headers=headers)
    assert r.status_code == 415 and r.json()["error"]["code"] == "unsupported_media_type"


def test_a_charset_parameter_and_a_mixed_case_content_type_are_fine(client):
    r = client.post(
        "/api/uploads",
        content=json.dumps(make_body()).encode(),
        headers={"content-type": "Application/JSON; charset=utf-8"},
    )
    assert r.status_code == 201


@pytest.mark.parametrize(
    "content, status, code",
    [
        (b"", 400, "invalid_json"),
        (b"[{", 400, "invalid_json"),
        (b"\xff\xfe", 400, "invalid_json"),
        (b"[NaN]", 400, "invalid_json"),
        (b"PK\x03\x04\x00\x00", 400, "invalid_json"),
        (b"[]", 400, "invalid_request"),
        (b'"a string"', 400, "invalid_request"),
        (b"{}", 400, "invalid_request"),
        (b'{"evidence": [], "decision": {}}', 400, "invalid_request"),
        (b'{"nope": 1}', 400, "invalid_request"),
    ],
)
def test_malformed_requests_get_the_envelope_and_a_code(client, content, status, code):
    r = client.post("/api/uploads", content=content, headers=JSON)
    assert r.status_code == status, r.text
    assert r.json()["error"]["code"] == code and r.json()["error"]["message"]


def test_invalid_request_details_name_fields_never_values(client):
    body = make_body(decision=one_claim_decision(severity="sentinel-severity"))
    body["decision"]["claims"][0]["parameters"] = {"sentinel-key": {"nested": "sentinel-value"}}
    r = create(client, body)
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_request"
    fields = r.json()["error"]["details"]["fields"]
    assert "decision.claims[0].severity" in fields and "decision.claims[0].parameters" in fields
    assert "sentinel" not in r.text
    bad = make_body()
    bad["evidence"][0]["kind"] = "sentinel-kind"
    bad["evidence"][0]["name"] = "../sentinel.json"
    r = create(client, bad)
    assert r.status_code == 400 and "sentinel" not in r.text
    assert set(r.json()["error"]["details"]["fields"]) == {"evidence[0].kind", "evidence[0].name"}


def test_ingestion_failures_are_reported_by_position_and_reason(client):
    r = create(client, make_body(content=[{"name": "sentinel-no-id"}]))
    error = r.json()["error"]
    assert r.status_code == 422 and error["code"] == "ingestion_failed" and error["details"]["evidenceIndex"] == 0
    assert "sentinel" not in r.text
    r = create(client, make_body(kind="tf-state", content={"version": 4}))
    assert r.status_code == 422 and r.json()["error"]["code"] == "ingestion_failed"


def test_an_invalid_decision_is_refused_by_claim_position(client):
    r = create(client, make_body(decision=one_claim_decision(detectorId="no-such-detector")))
    error = r.json()["error"]
    assert r.status_code == 422 and error["code"] == "invalid_decision"
    assert error["details"]["claimIndex"] == 0 and "region-allowed" in error["details"]["knownDetectors"]


def test_a_document_that_is_too_complex_is_refused(client):
    deep = {"data": [{"id": "/a", "name": "n", "type": "t", "properties": json.loads("[" * 80 + "]" * 80)}]}
    r = create(client, make_body(content=deep))
    assert (
        r.status_code == 422
        and r.json()["error"]["code"] == "too_complex"
        and r.json()["error"]["details"]["reason"] == "depth"
    )


def test_too_many_rows():
    with TestClient(create_app(make_settings(max_rows=3))) as c:
        rows = [{"id": f"/r{i}", "name": f"n{i}", "type": "t"} for i in range(4)]
        r = create(c, make_body(content=rows))
        assert r.status_code == 422 and r.json()["error"] == {
            "code": "too_many_rows",
            "message": "The files have more rows than the limit.",
            "details": {"evidenceIndex": 0, "maxRows": 3},
        }
        assert create(c, make_body(content=rows[:3])).status_code == 201


def test_the_body_is_capped_by_its_declared_length_and_while_it_streams():
    with TestClient(create_app(make_settings(max_upload_bytes=2000))) as c:
        r = c.post("/api/uploads", content=json.dumps(make_body()).encode(), headers=JSON)
        assert r.status_code == 413 and r.json()["error"]["code"] == "too_large"
        assert r.json()["error"]["details"] == {"maxUploadBytes": 2000}

        def chunks():
            for _ in range(20):
                yield b"[" + b" " * 200

        r = c.post("/api/uploads", content=chunks(), headers=JSON | {"transfer-encoding": "chunked"})
        assert r.status_code == 413


def test_a_slow_body_is_cut_off_at_the_deadline(monkeypatch):
    monkeypatch.setattr(uploads, "READ_DEADLINE_SECONDS", 0.05)
    app = create_app(make_settings())

    async def endless(request, limit, *, deadline_seconds=None):
        from cloud_crawler_lab.security.limits import read_body as real

        class Slow:
            headers = {}

            async def stream(self):
                while True:
                    await asyncio.sleep(0.2)
                    yield b" "

        assert deadline_seconds == 0.05
        return await real(Slow(), limit, deadline_seconds=deadline_seconds)

    monkeypatch.setattr(uploads, "read_body", endless)
    with TestClient(app) as c:
        r = create(c)
        assert r.status_code == 408 and r.json()["error"]["code"] == "request_timeout"


def test_rate_limit_answers_429_with_retry_after_and_ignores_forwarded_for_by_default():
    with TestClient(create_app(make_settings(rate_limit_posts=2, rate_limit_window_minutes=10))) as c:
        assert create(c).status_code == 201 and create(c).status_code == 201
        r = create(c)
        assert (
            r.status_code == 429 and r.json()["error"]["code"] == "rate_limited" and int(r.headers["retry-after"]) >= 1
        )
        assert create(c, headers={"x-forwarded-for": "203.0.113.9"}).status_code == 429
    with TestClient(create_app(make_settings(rate_limit_posts=1, trust_proxy=True))) as c:
        assert create(c, headers={"x-forwarded-for": "203.0.113.1, 10.0.0.1"}).status_code == 201
        assert create(c, headers={"x-forwarded-for": "203.0.113.1"}).status_code == 429
        assert create(c, headers={"x-forwarded-for": "203.0.113.2"}).status_code == 201


def test_a_rate_limited_client_costs_no_verification_and_no_parsing(monkeypatch):
    calls = []
    app = create_app(
        make_settings(rate_limit_posts=1, turnstile_secret="s"), verifier=lambda r, t: calls.append(1) or b"{}"
    )
    monkeypatch.setattr(uploads, "process_upload", lambda *a, **k: pytest.fail("parsed"))
    with TestClient(app) as c:
        c.post("/api/uploads", content=b"x", headers=JSON)
        before = len(calls)
        assert c.post("/api/uploads", content=b"x", headers=JSON).status_code == 429
        assert len(calls) == before


def test_overloaded_when_every_evaluation_slot_is_taken():
    app = create_app(make_settings(max_concurrent=1))
    app.state.bound.wait_seconds = 0.05
    with TestClient(app) as c:
        asyncio.run(app.state.bound.acquire())
        r = create(c)
        assert r.status_code == 503 and r.json()["error"]["code"] == "overloaded" and r.headers["retry-after"] == "2"
        app.state.bound.release()
        assert create(c).status_code == 201


def test_an_unexpected_failure_is_a_plain_500_and_the_slot_is_released(monkeypatch):
    app = create_app(make_settings(max_concurrent=1))

    def boom(*args, **kwargs):
        raise RuntimeError("sentinel-secret /subscriptions/00000000-0000-0000-0000-000000000001")

    with TestClient(app, raise_server_exceptions=False) as c:
        monkeypatch.setattr(uploads, "process_upload", boom)
        r = create(c)
        assert r.status_code == 500 and r.json() == {
            "error": {"code": "internal_error", "message": "Something went wrong on our side."}
        }
        assert "sentinel" not in r.text
        monkeypatch.undo()
        assert create(c).status_code == 201, "the evaluation slot came back"


def test_the_oldest_results_go_first_when_the_item_limit_is_reached():
    app = create_app(make_settings(max_items=2, rate_limit_posts=100))
    app.state.store = UploadStore(7200, 2, 64 * 1024 * 1024, per_owner_items=100)
    with TestClient(app) as c:
        first, second, third = (create(c) for _ in range(3))
        assert c.get(f"/api/uploads/{first.json()['uploadId']}", headers=owner(first)).status_code == 404
        for item in (second, third):
            assert c.get(f"/api/uploads/{item.json()['uploadId']}", headers=owner(item)).status_code == 200


def test_one_client_cannot_push_another_clients_results_out(monkeypatch):
    app = create_app(make_settings(max_items=40, rate_limit_posts=1000, trust_proxy=True))
    with TestClient(app) as c:
        theirs = create(c, headers={"x-forwarded-for": "203.0.113.50"})
        mine = [create(c, headers={"x-forwarded-for": "198.51.100.7"}) for _ in range(6)]
        # a client holds a tenth of the items (4 of 40): its own oldest go, nobody else's
        assert [c.get(f"/api/uploads/{m.json()['uploadId']}", headers=owner(m)).status_code for m in mine] == [
            404,
            404,
            200,
            200,
            200,
            200,
        ]
        assert c.get(f"/api/uploads/{theirs.json()['uploadId']}", headers=owner(theirs)).status_code == 200


def test_results_expire_and_the_sweeper_removes_them(monkeypatch):
    monkeypatch.setattr(app_module, "SWEEP_SECONDS", 0.05)
    app = create_app(make_settings())
    app.state.store = UploadStore(0.15, 200, 64 * 1024 * 1024)
    with TestClient(app) as c:
        item = create(c)
        assert app.state.store.size == 1
        time.sleep(0.5)
        assert app.state.store.size == 0
        assert c.get(f"/api/uploads/{item.json()['uploadId']}", headers=owner(item)).status_code == 404


def test_shutdown_empties_the_store():
    app = create_app(make_settings())
    with TestClient(app) as c:
        create(c)
        assert app.state.store.size == 1
    assert app.state.store.size == 0


def test_each_upload_is_its_own_draft_decision(client):
    first, second = create(client), create(client)
    assert first.json()["decision"]["decisionId"] != second.json()["decision"]["decisionId"]
    assert first.json()["evidence"][0]["evidenceId"] != second.json()["evidence"][0]["evidenceId"]
    assert first.json()["evidence"][0]["payloadHash"] == second.json()["evidence"][0]["payloadHash"], (
        "the fingerprint is of content"
    )


def test_several_files_and_terraform_are_accepted_and_the_response_says_what_was_read(client):
    body = make_body()
    body["evidence"].append(
        {"kind": "tf-plan", "name": "plan.json", "content": {"format_version": "1.2", "resource_changes": [{}, {}]}}
    )
    r = create(client, body)
    assert r.status_code == 201
    [export, plan] = r.json()["evidence"]
    assert export["readByDetectors"] is True and plan["readByDetectors"] is False
    assert plan["entryCount"] == 2 and plan["resourceCount"] == 0 and plan["name"] == "plan.json"
    assert r.json()["summary"]["contradicted"] == 2


def test_a_claim_nothing_can_read_is_unknown_never_a_guess(client):
    only_terraform = {
        "evidence": [{"kind": "tf-state", "content": {"version": 4, "resources": [{}]}}],
        "decision": load_sample("decision-zone-redundancy.json"),
    }
    r = create(client, only_terraform)
    assert r.status_code == 201
    assert r.json()["summary"] == {
        "supported": 0,
        "contradicted": 0,
        "unknown": 1,
        "notApplicable": 0,
        "score": None,
        "coverage": 0.0,
    }
    detail = client.get(f"/api/uploads/{r.json()['uploadId']}", headers=owner(r)).json()
    assert (
        detail["findings"][0]["verdict"] == "unknown" and "no usable evidence" in detail["findings"][0]["unknownReason"]
    )


def test_samples_are_served_from_a_fixed_list(client):
    for name in (
        "sample-resource-graph.json",
        "decision-starter.json",
        "decision-zone-redundancy.json",
        "decision-wave-one.json",
    ):
        r = client.get(f"/api/samples/{name}")
        assert r.status_code == 200 and r.headers["content-type"] == "application/json"
        assert r.json() == load_sample(name) and r.headers["cache-control"] == "no-store"
    for name in (
        "README.md",
        "nope.json",
        "..%2Fpyproject.toml",
        "%2e%2e/pyproject.toml",
        "sample-resource-graph.json%00",
    ):
        assert client.get(f"/api/samples/{name}").status_code == 404, name
    assert client.get("/api/samples/").status_code == 404 and client.get("/api/samples").status_code == 404


def test_methods_the_routes_do_not_take_are_405_in_the_envelope(client, created):
    upload_id = created.json()["uploadId"]
    for method, path in (
        ("get", "/api/uploads"),
        ("put", "/api/uploads"),
        ("delete", "/api/uploads"),
        ("post", f"/api/uploads/{upload_id}"),
        ("put", f"/api/uploads/{upload_id}"),
        ("post", f"/api/uploads/{upload_id}/files/report.md"),
        ("post", "/api/samples/decision-starter.json"),
    ):
        r = getattr(client, method)(path)
        assert r.status_code == 405 and r.json()["error"]["code"] == "method_not_allowed", (method, path)


def test_cors_preflight_for_the_upload_allows_the_headers_the_pane_sends():
    app = create_app(make_settings(allowed_origins=("https://hybridcloudworks.com",)))
    with TestClient(app) as c:
        ok = c.options(
            "/api/uploads",
            headers={"origin": "https://hybridcloudworks.com", "access-control-request-method": "POST"},
        )
        assert ok.status_code == 204
        allowed = ok.headers["access-control-allow-headers"]
        assert "x-turnstile-token" in allowed and "x-owner-token" in allowed and "content-type" in allowed
        assert (
            "POST" in ok.headers["access-control-allow-methods"]
            and "DELETE" in ok.headers["access-control-allow-methods"]
        )
        bad = c.options(
            "/api/uploads", headers={"origin": "https://evil.example", "access-control-request-method": "POST"}
        )
        assert bad.status_code == 403


# ---- human verification -------------------------------------------------------------------------------------------


def siteverify(responses: dict[str, dict], seen: list | None = None):
    def opener(request, timeout):
        form = dict(pair.split("=", 1) for pair in request.data.decode().split("&"))
        if seen is not None:
            seen.append({"form": form, "thread": threading.get_ident()})
        return json.dumps(
            responses.get(form["response"], {"success": False, "error-codes": ["invalid-input-response"]})
        ).encode()

    return opener


GOOD = {"good": {"success": True, "action": TURNSTILE_ACTION}, "wrong-action": {"success": True, "action": "login"}}


def test_with_no_secret_and_no_override_uploads_fail_closed():
    with TestClient(create_app(make_settings(allow_no_turnstile=False))) as c:
        assert c.get("/api/health").json()["turnstile"]["required"] is True
        r = create(c)
        assert r.status_code == 503 and r.json()["error"]["code"] == "turnstile_not_configured"


def test_a_failed_closed_request_parses_nothing(monkeypatch):
    monkeypatch.setattr(uploads, "process_upload", lambda *a, **k: pytest.fail("the body was parsed"))
    monkeypatch.setattr(uploads, "read_body", lambda *a, **k: pytest.fail("the body was read"))
    with TestClient(create_app(make_settings(allow_no_turnstile=False))) as c:
        assert c.post("/api/uploads", content=b"not even json", headers=JSON).status_code == 503


def test_verification_comes_before_the_body_is_read_or_parsed(monkeypatch):
    monkeypatch.setattr(uploads, "process_upload", lambda *a, **k: pytest.fail("the body was parsed"))
    monkeypatch.setattr(uploads, "read_body", lambda *a, **k: pytest.fail("the body was read"))
    app = create_app(make_settings(turnstile_secret="the-secret"), verifier=siteverify(GOOD))
    with TestClient(app) as c:
        for headers in (
            {},
            {"x-turnstile-token": "bad"},
            {"x-turnstile-token": "wrong-action"},
            {"x-turnstile-token": "x" * 3000},
        ):
            r = c.post("/api/uploads", content=b"<not json at all>", headers=JSON | headers)
            assert r.status_code == 403 and r.json()["error"]["code"] == "turnstile_failed", headers
            assert "the-secret" not in r.text


def test_a_verified_request_goes_through_and_the_secret_and_address_reach_the_verifier_only():
    seen = []
    app = create_app(
        make_settings(turnstile_secret="the-secret", rate_limit_posts=100), verifier=siteverify(GOOD, seen)
    )
    with TestClient(app) as c:
        r = create(c, headers={"x-turnstile-token": "good"})
        assert r.status_code == 201 and "the-secret" not in r.text
        assert seen[0]["form"]["secret"] == "the-secret" and seen[0]["form"]["response"] == "good"
        assert seen[0]["form"]["remoteip"]
        assert c.get("/api/health").json()["turnstile"] == {"required": True, "siteKey": None}


def test_the_verification_call_runs_off_the_event_loop():
    seen, loop_thread = [], []
    app = create_app(make_settings(turnstile_secret="s"), verifier=siteverify(GOOD, seen))

    async def where():
        return {"thread": threading.get_ident()}

    app.router.routes.insert(0, APIRoute("/api/where", where, methods=["GET"]))
    with TestClient(app) as c:
        loop_thread.append(c.get("/api/where").json()["thread"])
        create(c, headers={"x-turnstile-token": "good"})
    assert seen and seen[0]["thread"] != loop_thread[0]


def test_the_override_only_applies_when_there_is_no_secret():
    # secret set: the override is ignored, verification is still required
    app = create_app(make_settings(turnstile_secret="s", allow_no_turnstile=True), verifier=siteverify(GOOD))
    with TestClient(app) as c:
        assert create(c).status_code == 403
        assert create(c, headers={"x-turnstile-token": "good"}).status_code == 201
    # no secret, override on: the documented local-only mode
    with TestClient(create_app(make_settings(allow_no_turnstile=True))) as c:
        assert c.get("/api/health").json()["turnstile"]["required"] is False
        assert create(c).status_code == 201


def test_a_verification_outage_refuses_the_upload():
    def down(request, timeout):
        raise TimeoutError

    with TestClient(create_app(make_settings(turnstile_secret="s"), verifier=down)) as c:
        r = create(c, headers={"x-turnstile-token": "good"})
        assert r.status_code == 403 and r.json()["error"]["details"]["codes"] == ["verification-unavailable"]


def test_a_result_bigger_than_the_whole_store_is_refused():
    app = create_app(make_settings())
    app.state.store = UploadStore(7200, 200, 100)  # 100 bytes: no report fits
    with TestClient(app) as c:
        r = create(c)
        assert r.status_code == 422 and r.json()["error"]["code"] == "result_too_large"


def test_a_result_past_the_per_item_cap_is_refused(monkeypatch):
    monkeypatch.setattr(analysis, "MAX_ITEM_BYTES", 1000)
    with TestClient(create_app(make_settings())) as c:
        r = create(c)
        assert r.status_code == 422 and r.json()["error"] == {
            "code": "result_too_large",
            "message": "The result is larger than the lab keeps.",
            "details": {"maxBytes": 1000},
        }


def test_a_sample_missing_from_the_samples_folder_is_not_found(tmp_path):
    with TestClient(create_app(make_settings(samples_dir=tmp_path))) as c:
        assert c.get("/api/samples/decision-starter.json").status_code == 404
