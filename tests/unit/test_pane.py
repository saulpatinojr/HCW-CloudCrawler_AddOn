"""The pane is static files; these hold what the lab's contract says about them. A real browser is not part of CI
(tests/e2e does not exist here); the run recorded in VALIDATION.md drove it with Playwright against a local lab."""

import re

from ..conftest import ROOT, SAMPLES

WEB = ROOT / "web"


def read(name: str) -> str:
    return (WEB / name).read_text(encoding="utf-8")


def test_uploads_are_open_in_the_pane():
    html, js = read("index.html"), read("app.js")
    for gone in (
        "first release of the upstream",
        "accepts no uploads",
        "ENGINE_NOTE",
        "the file picker below is disabled",
    ):
        assert gone not in html and gone not in js, gone
    assert not re.search(r'<input[^>]*id="file"[^>]*disabled', html), "the file picker is enabled"
    assert 'id="file"' in html and "multiple" in html
    assert "NOT-AN-AUDIT" in html or "not an audit" in html.lower()


def test_every_element_the_script_reaches_for_exists():
    html, js = read("index.html"), read("app.js")
    ids = set(re.findall(r"\$\('([\w-]+)'\)", js))
    assert ids, "the script looks elements up by id"
    missing = sorted(i for i in ids if f'id="{i}"' not in html)
    assert missing == [], missing


def test_the_pane_calls_only_the_labs_own_routes():
    js = read("app.js")
    paths = set(re.findall(r"'(/api/[^']*)'", js))
    assert paths == {"/api/health", "/api/samples/", "/api/uploads", "/api/uploads/"}
    for url in re.findall(r"https?://[^\s'\"]+", js):
        assert url.startswith("https://challenges."), url  # the human-verification script, loaded only with a site key
    assert "innerHTML" not in js and "outerHTML" not in js and "insertAdjacentHTML" not in js and "eval(" not in js


def test_the_samples_the_pane_names_exist_and_are_served():
    js = read("app.js")
    names = set(re.findall(r"'((?:decision|sample)[\w-]*\.json)'", js))
    assert names == {
        "sample-resource-graph.json",
        "decision-starter.json",
        "decision-zone-redundancy.json",
        "decision-wave-one.json",
    }
    from cloud_crawler_lab.routes.samples import SAMPLE_FILES

    assert names == set(SAMPLE_FILES)
    for name in re.findall(r'href="/api/samples/([\w.-]+)"', read("index.html")):
        assert name in SAMPLE_FILES


def test_the_served_samples_are_exactly_the_json_files_in_the_samples_folder():
    from cloud_crawler_lab.routes.samples import SAMPLE_FILES

    assert sorted(SAMPLE_FILES) == sorted(p.name for p in SAMPLES.glob("*.json"))


def test_the_pane_shows_the_note_and_the_expiry_in_words():
    html, js = read("index.html"), read("app.js")
    assert "expires after two hours" in html and "never asks for credentials" in html
    assert "Not an audit" in html and "audit-line" in js and "notAnAudit" in js
    assert "draft" in html.lower() and "Review notes" in html


def test_the_verification_action_matches_the_one_the_server_checks():
    from cloud_crawler_lab.config import TURNSTILE_ACTION

    assert f"var ACTION = '{TURNSTILE_ACTION}';" in read("app.js")
    assert "x-turnstile-token" in read("app.js") and "x-owner-token" in read("app.js")


def test_the_pane_sends_what_the_route_accepts():
    """The limits and kinds in the script are the server's."""
    from cloud_crawler_lab.evidence import FILE_NAME, KINDS, MAX_FILES

    js = read("app.js")
    assert f"var MAX_FILES = {MAX_FILES};" in js
    assert set(re.findall(r"'(arg-export|tf-state|tf-plan)'", js)) == set(KINDS)
    assert f"var NAME_OK = /{FILE_NAME}/;" in js, "the pane names files by the pattern the server accepts"


def test_the_pane_opens_no_browser_dialog_because_a_sandboxed_frame_may_not_be_allowed_to():
    """The sandbox in the integration guide has no `allow-modals`; a dialog there returns at once without asking."""
    js = read("app.js")
    for call in ("confirm(", "alert(", "prompt("):
        assert call not in js, call
    assert "Click again to delete" in js


def test_the_pane_reports_a_deletion_only_when_the_lab_says_it_happened():
    js = read("app.js")
    body = js[js.index("function deleteNow()") :]
    assert "if (!r.ok) throw new Error('delete');" in body
    assert body.index("if (!r.ok)") < body.index("state.result = null"), "the token is dropped only after a good answer"
    assert "could not be deleted" in body
