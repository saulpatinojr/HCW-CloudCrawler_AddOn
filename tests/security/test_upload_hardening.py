"""The upload route takes files from strangers. These tests are the ones that hold it to its promises: logs and error
messages never carry what was uploaded, nothing is written to disk, hostile documents get a clean refusal, and a
small upload cannot be turned into a large stored result."""

import ast
import builtins
import io
import json
import os
import sys
import time
from pathlib import Path
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from cloud_crawler_lab.app import create_app
from cloud_crawler_lab.routes import uploads
from cloud_crawler_lab.security import logging as logs
from cloud_crawler_lab.security.redaction import ALLOWED_WORDS

from ..conftest import JSON, ROOT, load_sample, make_body, make_settings, one_claim_decision

SRC = ROOT / "src" / "cloud_crawler_lab"
SENTINEL = "SENTINEL-4f7a91"
SUB = "/subscriptions/00000000-0000-0000-0000-000000000001"


def capture(monkeypatch) -> io.StringIO:
    buffer = io.StringIO()
    monkeypatch.setattr(sys, "stderr", buffer)
    return buffer


def assert_content_free(text: str, *, forbidden=()) -> list[dict]:
    lines = [json.loads(line) for line in text.splitlines() if line.strip()]
    for line in lines:
        for key, value in line.items():
            if key in ("ts", "scrubbed"):
                continue
            assert value is None or isinstance(value, bool | int | float) or value in ALLOWED_WORDS, (key, value)
    for word in (SENTINEL, "hcw-sample", "00000000-0000", "eastus", "centralus", "subscriptions", *forbidden):
        assert word not in text, word
    return lines


def loud_body() -> dict:
    """A request that carries the sentinel in every field a visitor controls, so a leak anywhere shows up."""
    export = load_sample("sample-resource-graph.json")
    for row in export["data"]:
        row["name"] = f"{SENTINEL}-{row['name']}"
        row["tags"][SENTINEL] = SENTINEL
        row["properties"]["note"] = SENTINEL
    decision = load_sample("decision-wave-one.json")
    decision.update(title=SENTINEL, context=SENTINEL, decision=SENTINEL, risks=[SENTINEL])
    for claim in decision["claims"]:
        claim["statement"] = f"{SENTINEL} {claim['statement']}"
        claim["selector"] = {"tagSelectors": {SENTINEL: SENTINEL}, "nameGlobs": [f"{SENTINEL}*"]}
    body = make_body(content=export, decision=decision, name=f"{SENTINEL}.json")
    return body


def test_logs_carry_counts_and_fixed_words_only_for_a_whole_session(monkeypatch):
    buffer = capture(monkeypatch)
    app = create_app(make_settings(log_silent=False, turnstile_secret="the-secret"), verifier=_always_good)
    with TestClient(app) as c:
        headers = {"x-turnstile-token": SENTINEL}
        created = c.post("/api/uploads", json=loud_body(), headers=headers)
        assert created.status_code == 201
        token, upload_id = created.json()["ownerToken"], created.json()["uploadId"]
        h = {"x-owner-token": token}
        c.get(f"/api/uploads/{upload_id}", headers=h)
        c.get(f"/api/uploads/{upload_id}/files/report.md", headers=h)
        c.get(f"/api/uploads/{upload_id}", headers={"x-owner-token": SENTINEL})
        c.delete(f"/api/uploads/{upload_id}", headers=h)
    lines = assert_content_free(buffer.getvalue(), forbidden=(token, upload_id, "the-secret"))
    events = [line["event"] for line in lines]
    assert events[0] == "startup" and events[-1] == "shutdown"
    assert "turnstile_verified" in events and "session_opened" in events and "session_closed" in events
    opened = next(line for line in lines if line["event"] == "session_opened")
    assert set(opened) == {
        "ts",
        "event",
        "files",
        "resources",
        "claims",
        "findings",
        "contradicted",
        "unknown",
        "proposals",
        "durationMs",
        "stored",
    }
    logs.configure(silent=True)


def _always_good(request, timeout):
    return json.dumps({"success": True, "action": "cloud-crawler-upload"}).encode()


@pytest.mark.parametrize(
    "send",
    [
        pytest.param(
            lambda c, b: c.post("/api/uploads", content=f"[{{ {SENTINEL}".encode(), headers=JSON), id="not json"
        ),
        pytest.param(
            lambda c, b: c.post("/api/uploads", content=SENTINEL.encode(), headers={"content-type": "text/plain"}),
            id="media type",
        ),
        pytest.param(lambda c, b: c.post("/api/uploads", json={SENTINEL: 1}), id="shape"),
        pytest.param(lambda c, b: c.post("/api/uploads", json=make_body(content=[{"name": SENTINEL}])), id="ingestion"),
        pytest.param(
            lambda c, b: c.post("/api/uploads", json=make_body(decision=one_claim_decision(detectorId=SENTINEL))),
            id="detector",
        ),
        pytest.param(
            lambda c, b: c.post(
                "/api/uploads",
                json=make_body(
                    decision=one_claim_decision(
                        detectorId="zone-redundancy",
                        expectation={"property": SENTINEL, "operator": "gte", "value": SENTINEL},
                    )
                ),
            ),
            id="claim",
        ),
        pytest.param(
            lambda c, b: c.post(
                "/api/uploads",
                json=make_body(
                    content={
                        "data": [
                            {
                                "id": "/a",
                                "name": "n",
                                "type": "t",
                                "properties": json.loads("[" * 80 + f'"{SENTINEL}"' + "]" * 80),
                            }
                        ]
                    }
                ),
            ),
            id="too deep",
        ),
        pytest.param(
            lambda c, b: c.post(
                "/api/uploads",
                json=make_body(kind="tf-state", content={"version": 4, "resources": [SENTINEL]}),
                headers={"x-turnstile-token": SENTINEL},
            ),
            id="terraform",
        ),
    ],
)
def test_a_refused_upload_logs_a_code_and_never_its_content(monkeypatch, send):
    buffer = capture(monkeypatch)
    with TestClient(create_app(make_settings(log_silent=False, rate_limit_posts=100))) as c:
        response = send(c, None)
        assert response.status_code in (400, 415, 422, 201), response.text
        assert SENTINEL not in response.text, "error messages repeat nothing the visitor uploaded"
    lines = assert_content_free(buffer.getvalue())
    if response.status_code != 201:
        rejected = next(line for line in lines if line["event"] == "upload_rejected")
        assert set(rejected) == {"ts", "event", "code", "status"} and rejected["status"] == response.status_code
    logs.configure(silent=True)


def test_other_refusals_and_failures_log_without_content(monkeypatch):
    buffer = capture(monkeypatch)
    app = create_app(
        make_settings(log_silent=False, turnstile_secret="the-secret", rate_limit_posts=3), verifier=_always_good
    )
    good = {"x-turnstile-token": "good"}
    with TestClient(app, raise_server_exceptions=False) as c:
        assert c.post("/api/uploads", json=make_body(), headers={"x-turnstile-token": ""}).status_code == 403
        boom = RuntimeError(f"{SENTINEL} /subscriptions/x")
        with mock.patch.object(uploads, "process_upload", side_effect=boom):
            response = c.post("/api/uploads", json=make_body(), headers=good)
        assert response.status_code == 500 and SENTINEL not in response.text
        assert c.post("/api/uploads", json=make_body(), headers=good).status_code == 201
        assert c.post("/api/uploads", json=make_body(), headers=good).status_code == 429
    lines = assert_content_free(buffer.getvalue(), forbidden=("the-secret",))
    failed = next(line for line in lines if line["event"] == "upload_failed")
    assert failed["scrubbed"] == "RuntimeError", "the exception's class is logged, never its message"
    codes = [line["code"] for line in lines if line["event"] == "upload_rejected"]
    assert codes == ["turnstile_failed", "internal_error", "rate_limited"]
    logs.configure(silent=True)


def test_nothing_is_written_to_disk_while_an_upload_runs(monkeypatch, tmp_path):
    written = []
    real_open, real_os_open = builtins.open, os.open

    def guarded_open(file, mode="r", *args, **kwargs):
        if any(flag in str(mode) for flag in "wax+"):
            written.append(file)
        return real_open(file, mode, *args, **kwargs)

    def guarded_os_open(path, flags, *args, **kwargs):
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC):
            written.append(path)
        return real_os_open(path, flags, *args, **kwargs)

    monkeypatch.chdir(tmp_path)
    before = sorted(p.name for p in tmp_path.iterdir())
    with TestClient(create_app(make_settings())) as c:
        monkeypatch.setattr(builtins, "open", guarded_open)
        monkeypatch.setattr(os, "open", guarded_os_open)
        created = c.post("/api/uploads", json=make_body())
        headers = {"x-owner-token": created.json()["ownerToken"]}
        c.get(f"/api/uploads/{created.json()['uploadId']}", headers=headers)
        c.get(f"/api/uploads/{created.json()['uploadId']}/files/report.md", headers=headers)
        c.delete(f"/api/uploads/{created.json()['uploadId']}", headers=headers)
        c.post("/api/uploads", json={"nope": 1})
    assert created.status_code == 201 and written == []
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def python_files():
    return [p for p in SRC.rglob("*.py")]


def imported_roots(path: Path) -> set[str]:
    roots = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_the_source_has_no_way_to_write_a_file_or_to_run_a_program():
    banned_modules = {
        "tempfile",
        "shutil",
        "sqlite3",
        "shelve",
        "pickle",
        "marshal",
        "subprocess",
        "multiprocessing",
        "ctypes",
    }
    banned_calls = {"write_text", "write_bytes", "mkdir", "touch", "unlink", "rmdir", "chmod", "system", "popen"}
    for path in python_files():
        assert not imported_roots(path) & banned_modules, path
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                assert name not in banned_calls, f"{path.name}: {name}"
                if name == "open":
                    mode = node.args[1].value if len(node.args) > 1 and isinstance(node.args[1], ast.Constant) else "r"
                    assert not any(flag in str(mode) for flag in "wax+"), f"{path.name} opens a file for writing"


def test_the_source_loads_nothing_that_can_run_code_and_opens_no_archive():
    banned = {
        "yaml",
        "ruamel",
        "pickle",
        "marshal",
        "zipfile",
        "tarfile",
        "gzip",
        "bz2",
        "lzma",
        "zlib",
        "xml",
        "lxml",
        "defusedxml",
        "csv",
        "re",
    }
    for path in python_files():
        assert not imported_roots(path) & banned, f"{path.name} imports {sorted(imported_roots(path) & banned)}"
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {"eval", "exec", "compile", "__import__"}, f"{path.name}: {node.func.id}"


def test_the_one_pattern_in_the_upload_models_is_a_plain_character_class():
    """It runs in pydantic's linear-time engine, and it has no group, no alternation and no nested quantifier."""
    from cloud_crawler_lab.evidence import FILE_NAME

    assert FILE_NAME == r"^[\w .()-]{1,120}\.json$"
    assert not any(token in FILE_NAME for token in ("(?", "|", "+)", "*)", "){"))


def test_every_logged_word_is_in_the_allowed_list():
    """The log writer would raise at run time; this finds the unwritten branch before a visitor does."""
    for path in python_files():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (
                isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", "")) == "log_event"
            ):
                continue
            first = node.args[0]
            assert isinstance(first, ast.Constant) and first.value in ALLOWED_WORDS, (path.name, ast.dump(first))
            for kw in node.keywords:
                if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str) and kw.arg != "scrubbed":
                    assert kw.value.value in ALLOWED_WORDS, (path.name, kw.arg, kw.value.value)


@pytest.fixture
def lab():
    with TestClient(create_app(make_settings(rate_limit_posts=1000))) as c:
        yield c


def test_hostile_documents_get_a_clean_refusal_and_never_a_server_error(lab):
    big_int = "9" * 4000
    cases = {
        "nan": b'{"evidence":[{"kind":"arg-export","content":[NaN]}],"decision":{}}',
        "infinity": b'{"evidence":[{"kind":"arg-export","content":[1e999]}],"decision":{}}',
        "huge int": b'{"evidence":[{"kind":"arg-export","content":[' + big_int.encode() + b']}],"decision":{}}',
        "lone surrogate": b'{"evidence":[{"kind":"arg-export","content":["\\ud800"]}],"decision":{}}',
        "bom then garbage": b"\xef\xbb\xbf\x00\x01",
        "deeply nested": b"[" * 100_000 + b"]" * 100_000,
        "nested objects": b'{"a":' * 50_000 + b"1" + b"}" * 50_000,
        "empty containers": b"[" + b"[]," * 200_000 + b"[]]",
        "zip magic": b"PK\x03\x04" + os.urandom(64),
        "gzip magic": b"\x1f\x8b\x08" + os.urandom(64),
        "yaml": b"!!python/object/apply:os.system ['id']\n",
        "xml bomb": b'<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaa">]><l>&a;&a;&a;</l>',
        "null bytes": b"\x00" * 1000,
    }
    for name, body in cases.items():
        started = time.perf_counter()
        r = lab.post("/api/uploads", content=body, headers=JSON)
        assert r.status_code in (400, 422), (name, r.status_code, r.text[:200])
        assert r.json()["error"]["code"] in ("invalid_json", "invalid_request", "too_complex"), name
        assert time.perf_counter() - started < 5, name


def test_a_decision_cannot_smuggle_a_container_into_the_engines_comparisons(lab):
    for expectation in (
        {"property": "location", "operator": "in", "value": [{"a": 1}]},
        {"property": "location", "operator": "in", "value": [["a"]]},
        {"property": "location", "operator": "eq", "value": {"a": 1}},
        {"property": "location", "operator": "in", "value": "not-a-list"},
    ):
        r = lab.post("/api/uploads", json=make_body(decision=one_claim_decision(expectation=expectation)))
        assert r.status_code in (400, 422), (expectation, r.status_code)


WEIRD = [None, True, 7, 1.5, "", "Enabled", [], {}, [None], [[]], {"a": {"b": []}}, ["x"] * 3, "z" * 600, 10**30, -1]


def test_odd_property_shapes_never_reach_a_server_error(lab):
    """Every property any resource detector reads, set to every odd shape, against a claim from every detector."""
    types = [
        "microsoft.sql/servers/databases",
        "microsoft.storage/storageaccounts",
        "microsoft.web/serverfarms",
        "microsoft.web/sites",
        "microsoft.dbforpostgresql/flexibleservers",
        "microsoft.documentdb/databaseaccounts",
        "microsoft.containerservice/managedclusters",
        "microsoft.compute/virtualmachines",
        "microsoft.network/publicipaddresses",
        "microsoft.keyvault/vaults",
        "microsoft.sql/servers",
    ]
    rows = []
    for i, value in enumerate(WEIRD):
        for t in types:
            rows.append(
                {
                    "id": f"{SUB}/resourceGroups/rg/providers/{t}/r{i}",
                    "name": f"r{i}",
                    "type": t,
                    "location": value,
                    "sku": value,
                    "identity": value,
                    "tags": value,
                    "zones": value,
                    "properties": {
                        "zoneRedundant": value,
                        "publicNetworkAccess": value,
                        "privateEndpointConnections": value,
                        "highAvailability": value,
                        "locations": value,
                        "agentPoolProfiles": value,
                        "apiServerAccessProfile": value,
                        "network": value,
                    },
                }
            )
    claims = [
        {
            "detectorId": "zone-redundancy",
            "expectation": {"property": "zoneRedundant", "operator": "eq", "value": True},
        },
        {"detectorId": "public-access-disabled", "expectation": {"property": "p", "operator": "eq", "value": True}},
        {"detectorId": "private-endpoint-present", "expectation": {"property": "p", "operator": "eq", "value": True}},
        {"detectorId": "managed-identity", "expectation": {"property": "p", "operator": "eq", "value": True}},
        {
            "detectorId": "managed-identity",
            "parameters": {"identityType": "UserAssigned"},
            "expectation": {"property": "p", "operator": "eq", "value": True},
        },
        {
            "detectorId": "tag-required",
            "parameters": {"tag": "owner"},
            "expectation": {"property": "tag", "operator": "exists"},
        },
        {"detectorId": "sku-allowed", "expectation": {"property": "sku", "operator": "in", "value": ["a", 1]}},
        {
            "detectorId": "region-allowed",
            "expectation": {"property": "location", "operator": "in", "value": ["a", None]},
        },
        {"detectorId": "advisor-findings", "expectation": {"property": "openFindings", "operator": "eq", "value": 0}},
        {
            "detectorId": "retirement-exposure",
            "expectation": {"property": "exposedResources", "operator": "eq", "value": 0},
        },
        {
            "detectorId": "policy-assignment-present",
            "parameters": {"policyDefinitionId": "x"},
            "expectation": {"property": "assigned", "operator": "eq", "value": True},
        },
    ]
    decision = {"title": "t", "claims": [{"statement": "s", **claim} for claim in claims]}
    r = lab.post("/api/uploads", json=make_body(content=rows, decision=decision))
    assert r.status_code in (201, 422), r.text[:300]
    if r.status_code == 422:
        assert r.json()["error"]["code"] in ("ingestion_failed", "too_complex", "invalid_decision")


def storage_rows(count: int) -> list[dict]:
    return [
        {
            "id": f"{SUB}/resourceGroups/rg/providers/microsoft.storage/storageaccounts/s{i}",
            "name": f"s{i}",
            "type": "microsoft.storage/storageaccounts",
            "location": "centralus",
            "sku": {"name": "Standard_LRS"},
            "properties": {"publicNetworkAccess": "Enabled", "note": "n" * 400},
        }
        for i in range(count)
    ]


def public_access_decision(claims: int) -> dict:
    claim = {
        "statement": "s",
        "detectorId": "public-access-disabled",
        "expectation": {"property": "p", "operator": "eq", "value": True},
    }
    return {"title": "t", "claims": [claim] * claims}


def test_a_small_upload_cannot_become_a_large_stored_result():
    """5,000 resources and 5 claims make 25,000 findings; what is kept stays small and says what it left out."""
    app = create_app(make_settings())
    with TestClient(app) as c:
        started = time.perf_counter()
        r = c.post("/api/uploads", json=make_body(content=storage_rows(5000), decision=public_access_decision(5)))
        elapsed = time.perf_counter() - started
        assert r.status_code == 201, r.text[:300]
        listing = r.json()["listing"]
        assert listing["findingsTotal"] == 25_000 and listing["findingsListed"] == 1000
        assert listing["findingsLeftOut"] == 24_000
        assert r.json()["summary"]["contradicted"] == 25_000, "the counts are exact even though the list is short"
        assert app.state.store.bytes_used < 8 * 1024 * 1024
        assert len(r.content) < 200_000
        headers = {"x-owner-token": r.json()["ownerToken"]}
        detail = c.get(f"/api/uploads/{r.json()['uploadId']}", headers=headers)
        assert len(detail.json()["findings"]) == 1000 and len(detail.json()["contradictions"]) == 1000
        assert all(len(p["impactedResourceIds"]) <= 100 for p in detail.json()["proposals"])
        md = c.get(f"/api/uploads/{r.json()['uploadId']}/files/report.md", headers=headers).text
        assert "24000 more are left out" in md and len(md) < 2_000_000
    assert elapsed < 60


def test_claims_times_resources_is_capped_before_the_engine_evaluates_anything(monkeypatch):
    """The engine holds every finding while it works, about 3.6 KB each; the cap keeps two evaluations inside 512 MB."""
    from cloud_crawler_lab import analysis

    assert analysis.MAX_FINDINGS == 25_000
    with TestClient(create_app(make_settings())) as c:
        monkeypatch.setattr(analysis, "evaluate_decision", lambda *a, **k: pytest.fail("evaluated"))
        r = c.post("/api/uploads", json=make_body(content=storage_rows(5000), decision=public_access_decision(6)))
        assert r.status_code == 422 and r.json()["error"] == {
            "code": "too_many_findings",
            "message": "Claims times resources is more than the lab evaluates at once; use fewer of either.",
            "details": {"claims": 6, "resources": 5000, "maxFindings": 25_000},
        }
        monkeypatch.undo()
        ok = c.post("/api/uploads", json=make_body(content=storage_rows(1250), decision=public_access_decision(20)))
        assert ok.status_code == 201 and ok.json()["listing"]["findingsTotal"] == 25_000
        # Terraform files read into no resources, so they never count against it
        tf = make_body(
            kind="tf-state", content={"version": 4, "resources": [{}] * 5000}, decision=public_access_decision(20)
        )
        assert c.post("/api/uploads", json=tf).status_code == 201


def test_a_value_echoed_in_a_finding_is_shortened_when_it_is_large():
    export = [
        {
            "id": f"{SUB}/resourceGroups/rg/providers/microsoft.keyvault/vaults/v",
            "name": "v",
            "type": "microsoft.keyvault/vaults",
            "properties": {"publicNetworkAccess": "x" * 50_000},
        }
    ]
    claim = {"detectorId": "public-access-disabled", "expectation": {"property": "p", "operator": "eq", "value": True}}
    with TestClient(create_app(make_settings())) as c:
        r = c.post(
            "/api/uploads",
            json=make_body(content=export, decision={"title": "t", "claims": [{"statement": "s", **claim}]}),
        )
        detail = c.get(f"/api/uploads/{r.json()['uploadId']}", headers={"x-owner-token": r.json()["ownerToken"]}).json()
    [finding] = detail["findings"]
    assert finding["verdict"] == "unknown" and finding["observed"]["truncated"] is True
    assert len(json.dumps(detail)) < 20_000


def test_the_report_says_the_edition_cannot_reach_azure(lab):
    r = lab.post("/api/uploads", json=make_body())
    headers = {"x-owner-token": r.json()["ownerToken"]}
    report = lab.get(f"/api/uploads/{r.json()['uploadId']}/files/report.json", headers=headers).json()
    assert report["lab"]["callsAzure"] is False
    assert lab.get(f"/api/uploads/{r.json()['uploadId']}", headers=headers).json()["engine"]["callsAzure"] is False
