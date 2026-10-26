from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from cloud_crawler_lab import __version__
from cloud_crawler_lab.app import api_routes, create_app
from cloud_crawler_lab.errors import ApiError
from cloud_crawler_lab.security.headers import VERIFICATION_ORIGIN

from ..conftest import make_settings

# Only ever added to, in this order (the website's status proxy reads the list).
CAPABILITIES = [
    "health",
    "pane",
    "upload-evidence",
    "drift-findings",
    "draft-decision-record",
    "review-proposals",
    "report-markdown",
    "report-json",
    "not-an-audit",
    "sample-data",
    "delete-now",
]


def test_health_is_flat_and_complete(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["id"] == "cloud-crawler" and body["version"] == __version__
    assert body["edition"] == "lab" and body["azureConnectivity"] == "disabled-by-design" and "addon" not in body
    assert body["turnstile"] == {"required": False, "siteKey": None} and body["siteOrigins"] == [
        "https://hybridcloudworks.com"
    ]
    assert body["limits"] == {"maxUploadBytes": 5242880, "maxRows": 5000, "ttlMinutes": 120}
    assert body["asOf"].endswith("Z") and body["capabilities"] == CAPABILITIES
    assert r.headers["x-addon-id"] == "cloud-crawler" and r.headers["x-addon-version"] == __version__
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["cache-control"] == "no-store" and r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]


def test_health_reports_verification_as_required_when_fail_closed():
    with TestClient(create_app(make_settings(allow_no_turnstile=False))) as c:
        assert c.get("/api/health").json()["turnstile"] == {"required": True, "siteKey": None}
    with TestClient(create_app(make_settings(turnstile_secret="s", turnstile_site_key="k"))) as c:
        r = c.get("/api/health")
        assert r.json()["turnstile"] == {"required": True, "siteKey": "k"}
        assert VERIFICATION_ORIGIN in r.headers["content-security-policy"]


def test_documented_api_surface(client):
    assert api_routes(client.app) == {
        "/api/health": {"GET"},
        "/api/uploads": {"POST"},
        "/api/uploads/{upload_id}": {"GET", "DELETE"},
        "/api/uploads/{upload_id}/files/{name}": {"GET"},
        "/api/samples/{name}": {"GET"},
    }


def test_unknown_api_paths_and_wrong_methods_use_the_envelope(client):
    r = client.get("/api/nothing")
    assert r.status_code == 404 and r.json() == {"error": {"code": "not_found", "message": "Not found."}}
    r = client.post("/api/health")
    assert r.status_code == 405 and r.json()["error"]["code"] == "method_not_allowed"
    r = client.get("/api")
    assert r.status_code == 404
    assert client.get("/api/health", headers={"accept": "text/html"}).status_code == 200


def test_pane_is_served_and_stays_under_the_static_directory(client):
    r = client.get("/")
    assert r.status_code == 200 and "no cloud connectivity by design" in r.text and "Not production" in r.text
    assert r.headers["content-type"].startswith("text/html") and r.headers["cache-control"] == "no-cache"
    assert "never asks for credentials" in r.text and "expires after two hours" in r.text
    js = client.get("/app.js")
    assert js.status_code == 200 and "hcw-addon" in js.text and "'cloud-crawler'" in js.text
    assert js.headers["cache-control"] == "public, max-age=300"
    assert client.get("/theme.css").status_code == 200 and client.get("/styles.css").status_code == 200
    assert client.get("/missing.js").status_code == 404
    assert client.get("/../pyproject.toml").status_code == 404
    assert client.get("/%2e%2e/pyproject.toml").status_code == 404


def test_cors_is_exact_origin():
    app = create_app(make_settings(allowed_origins=("https://hybridcloudworks.com",)))
    with TestClient(app) as c:
        ok = c.options(
            "/api/health",
            headers={"origin": "https://hybridcloudworks.com", "access-control-request-method": "GET"},
        )
        assert ok.status_code == 204 and ok.headers["access-control-allow-origin"] == "https://hybridcloudworks.com"
        bad = c.options(
            "/api/health", headers={"origin": "https://evil.example", "access-control-request-method": "GET"}
        )
        assert bad.status_code == 403 and bad.json()["error"]["code"] == "forbidden"
        plain = c.get("/api/health", headers={"origin": "https://hybridcloudworks.com"})
        assert plain.headers["access-control-allow-origin"] == "https://hybridcloudworks.com"
        foreign = c.get("/api/health", headers={"origin": "https://evil.example"})
        assert "access-control-allow-origin" not in foreign.headers
        none = c.get("/api/health")
        assert "access-control-allow-origin" not in none.headers


def _prepend_route(app, path, endpoint):
    """Test routes go in front of the /api catch-all, where create_app's own routers sit."""
    app.router.routes.insert(0, APIRoute(path, endpoint, methods=["GET"]))


def test_unhandled_errors_are_enveloped_and_content_free():
    app = create_app(make_settings())

    async def boom():
        raise RuntimeError("secret /subscriptions/00000000-0000-0000-0000-000000000001")

    _prepend_route(app, "/api/boom", boom)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/api/boom")
        assert r.status_code == 500 and r.json() == {
            "error": {"code": "internal_error", "message": "Something went wrong on our side."}
        }
        assert "subscriptions" not in r.text


def test_api_error_body_matches_the_envelope():
    assert ApiError(404, "not_found", "Not found.").body() == {"error": {"code": "not_found", "message": "Not found."}}
    assert ApiError(413, "too_large", "x", {"maxUploadBytes": 1}).body()["error"]["details"] == {"maxUploadBytes": 1}


def test_validation_and_http_exceptions_are_enveloped():
    from fastapi import HTTPException

    app = create_app(make_settings())

    async def needs(n: int):
        if n == 7:
            raise HTTPException(status_code=403)
        return {"n": n}

    _prepend_route(app, "/api/needs/{n}", needs)
    with TestClient(app) as c:
        assert c.get("/api/needs/x").status_code == 400
        assert c.get("/api/needs/x").json()["error"]["code"] == "invalid_request"
        assert c.get("/api/needs/7").json()["error"] == {"code": "forbidden", "message": "The request was refused."}
        assert c.get("/api/needs/1").json() == {"n": 1}
