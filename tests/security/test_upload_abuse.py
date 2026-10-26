"""Abuse cases found by the independent security review of the upload route, each as a test that fails without its fix.

They are about cost, not content: a request that is small on the wire and large in memory or in time, and how many of
them one client can have in flight. The numbers (a few hundred thousand entries, a few megabytes) are the ones that
made the first version use over a gigabyte or stall the whole process for seconds."""

import asyncio
import json
import threading
import time
import tracemalloc
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.requests import ClientDisconnect

from cloud_crawler_lab import inputs
from cloud_crawler_lab.analysis import Outcome
from cloud_crawler_lab.app import create_app
from cloud_crawler_lab.errors import ApiError
from cloud_crawler_lab.routes import uploads
from cloud_crawler_lab.security.limits import client_address, read_body
from cloud_crawler_lab.security.ratelimit import ConcurrencyBound
from cloud_crawler_lab.security.redaction import ALLOWED_WORDS

from ..conftest import JSON, load_sample, make_body, make_settings, one_claim_decision

SUB = "/subscriptions/00000000-0000-0000-0000-000000000001"


def post_raw(client, body: bytes):
    return client.post("/api/uploads", content=body, headers=JSON)


def measured(call, *args, **kwargs):
    """(result, seconds, peak megabytes allocated by Python while the call ran)."""
    tracemalloc.start()
    started = time.perf_counter()
    try:
        result = call(*args, **kwargs)
        return result, time.perf_counter() - started, tracemalloc.get_traced_memory()[1] / 1e6
    finally:
        tracemalloc.stop()


@pytest.fixture
def lab():
    with TestClient(create_app(make_settings(rate_limit_posts=10_000))) as c:
        yield c


# ---- F1: validation errors are not allowed to grow with the request ----------------------------------------------


def decision_with(claim_patch: dict | None = None, **patch) -> dict:
    decision = one_claim_decision(**(claim_patch or {}))
    decision.update(patch)
    return decision


def test_a_huge_mapping_in_a_decision_is_refused_before_pydantic_builds_an_error_for_every_entry(lab):
    # lists are not scalars: one validation error each, and 250,000 of them used to be 1.3 GB. 90,000 fit under the
    # container bound, so the request-shape budget is what answers; 250,000 are answered by the container bound itself.
    for count, expected in ((90_000, (400, "invalid_request")), (250_000, (422, "too_complex"))):
        entries = {f"p{i}": [i] for i in range(count)}
        cases = {
            "parameters": decision_with({"parameters": entries}),
            "tag selectors": decision_with({"selector": {"tagSelectors": entries}}),
            "scope tag selectors": decision_with(scope={"tagSelectors": entries}),
        }
        for name, decision in cases.items():
            body = json.dumps(make_body(decision=decision)).encode()
            assert len(body) < 5 * 1024 * 1024, name
            response, seconds, peak = measured(post_raw, lab, body)
            assert (response.status_code, response.json()["error"]["code"]) == expected, (count, name)
            assert seconds < 3 and peak < 80, (count, name, seconds, peak)
    flat = {
        "top-level keys": {**one_claim_decision(), **{f"k{i}": 1 for i in range(200_000)}},
        "many values": decision_with({"expectation": {"property": "p", "operator": "in", "value": ["v"] * 400_000}}),
        "many claims": {"title": "t", "claims": one_claim_decision()["claims"] * 25_000},
    }
    for name, decision in flat.items():
        body = json.dumps(make_body(decision=decision)).encode()
        assert len(body) < 5 * 1024 * 1024, name
        response, seconds, peak = measured(post_raw, lab, body)
        assert response.status_code in (400, 422), name
        assert seconds < 3 and peak < 80, (name, seconds, peak)


def test_extra_keys_next_to_the_evidence_and_the_files_are_refused_early(lab):
    for body in (
        {**make_body(), **{f"k{i}": 1 for i in range(100_000)}},
        {"evidence": [{**make_body()["evidence"][0], **{f"k{i}": 1 for i in range(100_000)}}], "decision": {}},
    ):
        response, seconds, peak = measured(post_raw, lab, json.dumps(body).encode())
        assert response.status_code == 400 and seconds < 3 and peak < 80


# ---- F2: the engine's secret-shape pattern is quadratic on repeated `eyJ` ----------------------------------------


def test_a_string_that_repeats_the_token_prefix_is_refused_so_the_engines_pattern_stays_linear(lab):
    hostile = "eyJ" * 21_845
    rows = [{"id": f"{SUB}/r{i}", "name": "n", "type": "t", "properties": {"a": hostile}} for i in range(40)]
    response, seconds, _ = measured(lab.post, "/api/uploads", json=make_body(content=rows))
    assert response.status_code == 422 and response.json()["error"]["details"]["reason"] == "token_shapes"
    assert seconds < 3


def test_a_real_token_shape_is_still_accepted_and_redacted(lab):
    token = "eyJ" + "a" * 20 + "." + "b" * 20 + "." + "c" * 20
    rows = [{"id": f"{SUB}/r", "name": "n", "type": "t", "properties": {"note": f"x {token}"}}]
    response = lab.post("/api/uploads", json=make_body(content=rows))
    assert response.status_code == 201 and response.json()["evidence"][0]["redactedCount"] == 1
    assert inputs.MAX_TOKEN_STARTS >= 3


def test_no_thread_is_stalled_for_long_by_the_hostile_string():
    """What the review measured: one uninterrupted stall of 1.1 s while the pattern ran with the GIL held."""
    stalls, stop = [], threading.Event()

    def ticker():
        last = time.perf_counter()
        while not stop.is_set():
            time.sleep(0.005)
            now = time.perf_counter()
            stalls.append(now - last)
            last = now

    thread = threading.Thread(target=ticker)
    thread.start()
    try:
        rows = [{"id": f"{SUB}/r{i}", "name": "n", "type": "t", "properties": {"a": "eyJ" * 21_845}} for i in range(5)]
        with TestClient(create_app(make_settings())) as c:
            assert c.post("/api/uploads", json=make_body(content=rows)).status_code == 422
    finally:
        stop.set()
        thread.join()
    assert max(stalls) < 0.5


# ---- F4: the engine keeps three copies of what it reads ----------------------------------------------------------


def test_a_document_of_hundreds_of_thousands_of_tiny_objects_is_refused_cheaply(lab):
    tiny = [{"a": 1}] * 385_000
    rows = [{"id": f"{SUB}/r", "name": "n", "type": "t", "properties": {"x": tiny}}]
    body = json.dumps(make_body(content=rows)).encode()
    assert len(body) < 5 * 1024 * 1024
    response, seconds, peak = measured(post_raw, lab, body)
    assert response.status_code == 422 and response.json()["error"]["details"]["reason"] == "containers"
    assert seconds < 2 and peak < 60


def test_the_largest_realistic_upload_stays_inside_the_memory_the_lab_host_gives_it():
    """5,000 resources of ordinary shape and 5 claims (25,000 findings), the most the cap on claims times resources
    allows. Two evaluations run at once, so one must stay well under half of the 512 MB of the lab host's container."""
    rows = [
        {
            "id": f"{SUB}/resourceGroups/rg{i % 50}/providers/microsoft.storage/storageaccounts/s{i}",
            "name": f"s{i}",
            "type": "microsoft.storage/storageaccounts",
            "location": "centralus",
            "tags": {"env": "prod", "owner": "x"},
            "sku": {"name": "Standard_LRS"},
            "properties": {"publicNetworkAccess": "Enabled", "pad": "p" * 500, "privateEndpointConnections": []},
        }
        for i in range(5000)
    ]
    claim = {
        "statement": "s",
        "detectorId": "public-access-disabled",
        "expectation": {"property": "p", "operator": "eq", "value": True},
    }
    body = json.dumps(make_body(content={"count": 5000, "data": rows}, decision={"title": "t", "claims": [claim] * 5}))
    from cloud_crawler_lab.analysis import process_upload

    outcome, seconds, peak = measured(process_upload, body.encode(), max_rows=5000)
    assert outcome.meta["listing"]["findingsTotal"] == 25_000
    assert peak < 160, f"{peak:.0f} MB allocated by one evaluation"
    assert seconds < 90


# ---- F3: the key a client is rate limited by ---------------------------------------------------------------------


def fake_request(forwarded: str | None, peer: str = "198.51.100.9"):
    headers = {"x-forwarded-for": forwarded} if forwarded is not None else {}
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=peer))


def test_the_forwarded_address_is_used_only_when_it_is_an_address():
    assert client_address(fake_request("203.0.113.5, 10.0.0.1"), True) == "203.0.113.5"
    for garbage in ("", "not an address", "1.2.3", "203.0.113.5.7", "<script>", "unknown", "x" * 500):
        assert client_address(fake_request(garbage), True) == "198.51.100.9", garbage
    assert client_address(fake_request(None), True) == "198.51.100.9"
    assert client_address(fake_request("203.0.113.5"), False) == "198.51.100.9", "ignored unless the proxy is trusted"


def test_an_ipv6_client_is_one_client_per_64():
    a = client_address(fake_request("2001:db8:1:2:aaaa:bbbb:cccc:1"), True)
    b = client_address(fake_request("2001:db8:1:2:ffff:eeee:dddd:2"), True)
    other = client_address(fake_request("2001:db8:1:3::1"), True)
    assert a == b == "2001:db8:1:2::/64" and other != a
    assert client_address(fake_request(None, peer="2001:db8::1"), False) == "2001:db8::/64"


def test_garbage_in_the_forwarded_header_does_not_buy_a_fresh_bucket():
    app = create_app(make_settings(rate_limit_posts=3, trust_proxy=True))
    with TestClient(app) as c:
        statuses = [
            c.post("/api/uploads", json=make_body(), headers={"x-forwarded-for": f"garbage-{i}"}).status_code
            for i in range(6)
        ]
    assert statuses.count(201) == 3 and statuses.count(429) == 3


# ---- F5: a client's share of the store ---------------------------------------------------------------------------


def test_a_client_that_uploads_a_lot_loses_its_own_oldest_results_not_other_peoples(lab):
    """Over the lab's real defaults: a client holds at most a tenth of 200 results."""
    app = create_app(make_settings(rate_limit_posts=10_000, trust_proxy=True))
    with TestClient(app) as c:
        victim = c.post("/api/uploads", json=make_body(), headers={"x-forwarded-for": "203.0.113.50"})
        for _ in range(45):
            c.post("/api/uploads", json=make_body(), headers={"x-forwarded-for": "198.51.100.7"})
        assert app.state.store.size == 1 + 20
        headers = {"x-owner-token": victim.json()["ownerToken"]}
        assert c.get(f"/api/uploads/{victim.json()['uploadId']}", headers=headers).status_code == 200


# ---- F6: what a detector scans for every claim -------------------------------------------------------------------


def test_a_row_with_a_great_many_tags_or_zones_is_refused(lab):
    def row(**more):
        return [{"id": f"{SUB}/r", "name": "n", "type": "t", **more}]

    ok = lab.post(
        "/api/uploads", json=make_body(content=row(tags={f"t{i}": "v" for i in range(100)}, zones=["1"] * 100))
    )
    assert ok.status_code == 201
    for more in ({"tags": {f"t{i}": "v" for i in range(101)}}, {"zones": ["1"] * 101}):
        response, seconds, _ = measured(lab.post, "/api/uploads", json=make_body(content=row(**more)))
        assert response.status_code == 422 and response.json()["error"]["code"] == "ingestion_failed"
        assert seconds < 2


# ---- F8: a null parameter ----------------------------------------------------------------------------------------


def test_a_null_parameter_is_an_absent_one_and_never_a_server_error(lab):
    rows = [
        {"id": f"{SUB}/pip", "name": "pip", "type": "microsoft.network/publicipaddresses", "zones": ["1", "2", "3"]},
        {"id": f"{SUB}/aks", "name": "aks", "type": "microsoft.containerservice/managedclusters"},
    ]
    zone = {"detectorId": "zone-redundancy", "expectation": {"property": "z", "operator": "eq", "value": True}}
    for parameters in ({"minimumZones": None}, {"minimumZones": 3}, {"instanceSet": None}, {}):
        decision = decision_with({**zone, "parameters": parameters})
        response = lab.post("/api/uploads", json=make_body(content=rows, decision=decision))
        assert response.status_code == 201, (parameters, response.text[:200])
    decision = decision_with(
        {
            "detectorId": "tag-required",
            "parameters": {"tag": None},
            "expectation": {"property": "t", "operator": "exists"},
        }
    )
    refused = lab.post("/api/uploads", json=make_body(content=rows, decision=decision))
    assert refused.status_code == 422 and refused.json()["error"]["details"]["reason"] == "claim_not_evaluable"


# ---- F9: a client that goes away mid-body ------------------------------------------------------------------------


@pytest.mark.anyio
async def test_a_disconnect_while_the_body_arrives_is_a_handled_refusal():
    class Gone:
        headers = {}

        async def stream(self):
            yield b"abc"
            raise ClientDisconnect

    with pytest.raises(ApiError) as caught:
        await read_body(Gone(), 100, deadline_seconds=5)
    assert (caught.value.status, caught.value.code) == (400, "client_disconnected")
    assert "client_disconnected" in ALLOWED_WORDS


# ---- intake and evaluation slots ---------------------------------------------------------------------------------


def test_uploads_held_in_memory_at_once_are_bounded_before_the_body_is_read(monkeypatch):
    app = create_app(make_settings(max_concurrent=1))  # two places: one being evaluated, one waiting
    app.state.intake.wait_seconds = 0.01
    monkeypatch.setattr(uploads, "read_body", lambda *a, **k: pytest.fail("the body was read"))
    with TestClient(app) as c:
        asyncio.run(app.state.intake.acquire())
        asyncio.run(app.state.intake.acquire())
        response = c.post("/api/uploads", json=make_body())
        assert response.status_code == 503 and response.json()["error"]["code"] == "overloaded"
        assert response.headers["retry-after"] == "2"


def test_the_places_come_back_after_every_outcome():
    app = create_app(make_settings(max_concurrent=1, rate_limit_posts=1000))
    with TestClient(app) as c:
        for body in (make_body(), {"nope": 1}, make_body(decision=one_claim_decision(detectorId="no-such"))):
            for _ in range(3):
                c.post("/api/uploads", json=body)
        assert c.post("/api/uploads", json=make_body()).status_code == 201


@pytest.mark.anyio
async def test_a_cancelled_request_keeps_its_evaluation_slot_until_the_thread_has_really_finished(monkeypatch):
    started, release = threading.Event(), threading.Event()

    def slow(body, *, max_rows):
        started.set()
        release.wait(10)
        return Outcome({}, {})

    async def body_in(request, limit, *, deadline_seconds=None):
        return b"{}"

    monkeypatch.setattr(uploads, "process_upload", slow)
    monkeypatch.setattr(uploads, "read_body", body_in)
    state = SimpleNamespace(
        bound=ConcurrencyBound(1, wait_seconds=0.05),
        pool=ThreadPoolExecutor(max_workers=1),
        settings=make_settings(),
    )
    request = SimpleNamespace(app=SimpleNamespace(state=state))
    task = asyncio.create_task(uploads._read_and_evaluate(request))
    await asyncio.to_thread(started.wait, 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not await state.bound.acquire(), "the thread is still running, so the slot is still taken"
    release.set()
    await asyncio.sleep(0.2)
    assert await state.bound.acquire(), "and it comes back once the thread is done"
    state.pool.shutdown()


@pytest.mark.anyio
async def test_an_evaluation_that_fails_after_the_request_gave_up_leaves_no_unretrieved_error(monkeypatch):
    started, release = threading.Event(), threading.Event()

    def failing(body, *, max_rows):
        started.set()
        release.wait(10)
        raise RuntimeError("late failure")

    async def body_in(request, limit, *, deadline_seconds=None):
        return b"{}"

    monkeypatch.setattr(uploads, "process_upload", failing)
    monkeypatch.setattr(uploads, "read_body", body_in)
    loop = asyncio.get_running_loop()
    seen = []
    loop.set_exception_handler(lambda _loop, context: seen.append(context))
    state = SimpleNamespace(
        bound=ConcurrencyBound(1, wait_seconds=0.05), pool=ThreadPoolExecutor(max_workers=1), settings=make_settings()
    )
    task = asyncio.create_task(uploads._read_and_evaluate(SimpleNamespace(app=SimpleNamespace(state=state))))
    await asyncio.to_thread(started.wait, 5)
    task.cancel()
    release.set()
    await asyncio.sleep(0.2)
    import gc

    gc.collect()
    assert seen == []
    state.pool.shutdown()


def test_the_evaluations_run_in_threads_of_their_own(monkeypatch):
    names = []
    real = uploads.process_upload

    def spy(*args, **kwargs):
        names.append(threading.current_thread().name)
        return real(*args, **kwargs)

    monkeypatch.setattr(uploads, "process_upload", spy)
    with TestClient(create_app(make_settings())) as c:
        assert c.post("/api/uploads", json=make_body()).status_code == 201
    assert names and all(name.startswith("evaluate") for name in names)


def test_a_result_the_sample_decision_gives_is_the_same_through_the_pool(lab):
    r = lab.post("/api/uploads", json=make_body(decision=load_sample("decision-zone-redundancy.json")))
    assert r.json()["summary"]["contradicted"] == 2
