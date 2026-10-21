"""The health contract the website's status proxy reads (AddOn Integration Standard, sections 10 and 11)."""

from datetime import datetime

from cloud_crawler_lab import __version__

from ..conftest import ROOT

STATUS_PROXY_FIELDS = ("configured", "reachable", "version", "edition", "capabilities", "asOf")


def test_health_carries_every_field_the_status_proxy_projects(client):
    body = client.get("/api/health").json()
    for field in ("version", "edition", "capabilities", "asOf"):
        assert field in body, field
    assert isinstance(body["capabilities"], list) and all(isinstance(c, str) for c in body["capabilities"])
    datetime.fromisoformat(body["asOf"].replace("Z", "+00:00"))


def test_health_is_flat_with_id_and_version_at_the_top_level(client):
    body = client.get("/api/health").json()
    assert body["id"] == "cloud-crawler" and body["version"] == __version__
    assert set(body) == {
        "ok",
        "id",
        "version",
        "edition",
        "capabilities",
        "asOf",
        "siteOrigins",
        "turnstile",
        "azureConnectivity",
        "limits",
    }


def test_version_matches_pyproject():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f'version = "{__version__}"' in text


def test_pane_protocol_states_and_id():
    js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    assert "var ADDON_ID = 'cloud-crawler';" in js
    for state in ("'loading'", "'ready'", "'unavailable'"):
        assert f"post({state})" in js, state
    assert "window.parent.postMessage({ type: 'hcw-addon', id: ADDON_ID, state: paneState }, origin)" in js
    assert "state.siteOrigins.forEach" in js, "messages go to the published site origins only"
