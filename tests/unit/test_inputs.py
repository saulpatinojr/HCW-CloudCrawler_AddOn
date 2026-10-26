import json
import time

import pytest

from cloud_crawler_lab import inputs
from cloud_crawler_lab.errors import ApiError
from cloud_crawler_lab.inputs import MAX_DEPTH, check_bounds, parse_document


def nested(depth: int, leaf="x"):
    """A document with exactly `depth` levels of arrays around a leaf."""
    return json.loads("[" * depth + json.dumps(leaf) + "]" * depth)


def refused(call, *args) -> ApiError:
    with pytest.raises(ApiError) as caught:
        call(*args)
    return caught.value


def test_plain_json_parses_and_a_byte_order_mark_is_tolerated():
    assert parse_document(b'{"a": [1, 2.5, "x", null, true]}') == {"a": [1, 2.5, "x", None, True]}
    assert parse_document(b"\xef\xbb\xbf[1]") == [1]


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"[",
        b'{"a": }',
        b"\xff\xfe[]",  # not UTF-8
        b"[NaN]",
        b"[Infinity]",
        b"[-Infinity]",
        b"[1" + b"0" * 5000 + b"]",  # past the interpreter's integer-conversion limit
        b"<xml/>",
        b"PK\x03\x04" + b"\x00" * 40,  # a zip archive is not JSON, and is never opened
        b"key: value\n- item\n",  # YAML is not JSON, and is never loaded
    ],
)
def test_malformed_bodies_are_invalid_json_without_quoting_them(body):
    error = refused(parse_document, body)
    assert (error.status, error.code) == (400, "invalid_json")
    assert error.message == "The body is not valid JSON." and error.details is None


def test_deep_nesting_is_refused_not_crashed():
    """Python's JSON reader copes with thousands of levels; the engine's recursive readers (redaction, hashing) and
    pydantic should never be asked to. Either the pre-scan, the parser or the depth walk answers, never a crash."""

    def read(body: bytes):
        return check_bounds(parse_document(body))

    assert refused(read, b"[" * 200_000 + b"]" * 200_000).status in (400, 422)
    deep = b'{"a":' * 5_000 + b"1" + b"}" * 5_000
    error = refused(read, deep)
    assert (error.status, error.code) == (422, "too_complex") and error.details["reason"] == "depth"
    assert refused(read, b"[" * 100 + b"]" * 100).details["reason"] == "depth"


def test_the_container_bound_is_taken_from_the_bytes_before_parsing(monkeypatch):
    monkeypatch.setattr(inputs, "MAX_CONTAINERS", 10)
    parse_document(b"[[],[],[],[]]")  # 5 containers: fine
    error = refused(parse_document, b"[" * 11 + b"]" * 11)
    assert (error.status, error.code) == (422, "too_complex") and error.details["reason"] == "containers"


def test_depth_is_bounded_without_recursion():
    assert check_bounds(nested(MAX_DEPTH - 1)) > 0
    check_bounds(nested(MAX_DEPTH))
    error = refused(check_bounds, nested(MAX_DEPTH + 1))
    assert (error.status, error.code, error.details["reason"]) == (422, "too_complex", "depth")
    objects = {"k": 1}
    for _ in range(MAX_DEPTH + 1):
        objects = {"k": objects}
    assert refused(check_bounds, objects).details["reason"] == "depth"


def test_the_node_count_is_bounded(monkeypatch):
    monkeypatch.setattr(inputs, "MAX_NODES", 50)
    assert check_bounds(list(range(40))) == 41
    assert refused(check_bounds, list(range(60))).details["reason"] == "nodes"


def test_one_string_is_bounded(monkeypatch):
    monkeypatch.setattr(inputs, "MAX_STRING", 10)
    check_bounds({"k" * 10: "v" * 10})
    assert refused(check_bounds, ["v" * 11]).details["reason"] == "string_length"
    assert refused(check_bounds, {"k" * 11: 1}).details["reason"] == "string_length"


def test_numbers_that_json_cannot_carry_back_out_are_refused():
    assert refused(check_bounds, [float("inf")]).code == "invalid_json"
    assert refused(check_bounds, {"a": float("nan")}).code == "invalid_json"
    # `1e999` is legal JSON text that parses to infinity
    assert refused(lambda b: check_bounds(parse_document(b)), b"[1e999]").code == "invalid_json"
    check_bounds([1, -2, 3.5, 10**400, True, None])


def test_a_lone_surrogate_would_break_the_engines_hashing_so_it_is_refused_here():
    document = parse_document(b'["\\ud800"]')
    assert refused(check_bounds, document).code == "invalid_json"
    assert refused(check_bounds, {"\ud800": 1}).code == "invalid_json"
    check_bounds(parse_document(b'["\\ud83d\\ude00 \\u00e9"]'))  # a proper pair and an accent are fine


def test_the_walk_is_fast_on_a_realistic_large_document():
    rows = [
        {"id": f"/r/{i}", "name": f"n{i}", "tags": {"a": "b"}, "properties": {"x": [1, 2, 3], "y": {"z": "w"}}}
        for i in range(20_000)
    ]
    started = time.perf_counter()
    nodes = check_bounds(rows)
    assert nodes > 200_000 and time.perf_counter() - started < 5
