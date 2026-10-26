"""Bounded reading of an uploaded JSON document, before anything else looks at it.

The body has already been capped while it streamed in (`security/limits.py`). These checks cap what the bytes can
*become*: a few megabytes of brackets can build millions of objects, a deeply nested array can exhaust the stack of
every recursive reader downstream (the engine redacts and hashes recursively), and a number written as `1e999` is
not a number JSON can carry back out. All of them are answered with a content-free error before the engine sees
the document. Nothing here recurses, nothing here uses a regular expression, and nothing is written to disk.
"""

from __future__ import annotations

import json
import math
from typing import Any

from cloud_crawler_lab.errors import ApiError

# Nesting of arrays and objects, counting the document itself. Resource Graph properties are a dozen levels deep at
# most; the engine and pydantic recurse once per level, so this keeps every reader far from the interpreter's limit.
MAX_DEPTH = 64
# An upper bound on arrays plus objects, taken from the raw bytes before parsing (a bracket inside a string counts
# too, which only makes the bound stricter). A Resource Graph row is a handful of objects (tags, sku, identity,
# properties and what is nested in them), so 5,000 rows of 20 objects each fit. Past that, the engine's three copies of
# the document (parsed, redacted, normalised) measured 229 MB for one evaluation with 385,000 tiny objects in one row.
MAX_CONTAINERS = 100_000
# Every value in the parsed document: containers, strings, numbers, booleans and nulls.
MAX_NODES = 1_000_000
# The engine's secret-shape pattern (`eyJ...` then a dot) is quadratic on a string that repeats `eyJ` with no dot: every
# `eyJ` starts a scan to the end of the run. A real token has two or three. Refusing more than this keeps each string's
# cost linear, which matters because the engine redacts every string value of every upload.
MAX_TOKEN_STARTS = 16
# One string, in characters. Longer values are not evidence; they are a way to make results large.
MAX_STRING = 65_536


def _too_complex(reason: str) -> ApiError:
    return ApiError(
        422,
        "too_complex",
        "The document is more complex than the lab accepts.",
        {
            "reason": reason,
            "maxDepth": MAX_DEPTH,
            "maxContainers": MAX_CONTAINERS,
            "maxNodes": MAX_NODES,
            "maxStringLength": MAX_STRING,
        },
    )


def _reject_constant(_: str) -> Any:
    raise ValueError("NaN and Infinity are not JSON")


def parse_document(body: bytes) -> Any:
    """Bytes to a Python value. UTF-8 only (a byte-order mark is tolerated), strict JSON only."""
    if body.count(b"[") + body.count(b"{") > MAX_CONTAINERS:
        raise _too_complex("containers")
    try:
        return json.loads(body.decode("utf-8-sig"), parse_constant=_reject_constant)
    except ValueError, RecursionError:
        # UnicodeDecodeError, JSONDecodeError, a number too long to convert and NaN are all ValueErrors; a document
        # nested past the interpreter's limit is a RecursionError. None of their messages is repeated: they quote input.
        raise ApiError(400, "invalid_json", "The body is not valid JSON.") from None


def _check_text(value: str) -> None:
    if len(value) > MAX_STRING:
        raise _too_complex("string_length")
    if value.count("eyJ") > MAX_TOKEN_STARTS:
        raise _too_complex("token_shapes")
    if not value.isascii():
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            # A lone surrogate (`"\ud800"`) parses, but cannot be written back out as UTF-8: the engine hashes the
            # canonical form of everything it ingests.
            raise ApiError(400, "invalid_json", "The body is not valid JSON.") from None


def check_bounds(document: Any) -> int:
    """Walk the parsed document without recursion and refuse anything past the bounds. Returns the node count."""
    nodes = 0
    stack = [iter((document,))]  # one iterator per open container; the depth is the length of the stack
    while stack:
        try:
            node = next(stack[-1])
        except StopIteration:
            stack.pop()
            continue
        nodes += 1
        if nodes > MAX_NODES:
            raise _too_complex("nodes")
        if isinstance(node, dict):
            if len(stack) > MAX_DEPTH:
                raise _too_complex("depth")
            for key in node:
                _check_text(key)
            stack.append(iter(node.values()))
        elif isinstance(node, list):
            if len(stack) > MAX_DEPTH:
                raise _too_complex("depth")
            stack.append(iter(node))
        elif isinstance(node, str):
            _check_text(node)
        elif isinstance(node, float) and not math.isfinite(node):
            raise ApiError(400, "invalid_json", "The body is not valid JSON.")
    return nodes
