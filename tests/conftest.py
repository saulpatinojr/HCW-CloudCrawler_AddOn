from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from cloud_crawler_lab.app import create_app
from cloud_crawler_lab.config import Settings

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
JSON = {"content-type": "application/json"}


def make_settings(**overrides) -> Settings:
    base = {"allow_no_turnstile": True, "log_silent": True, "site_origins": ("https://hybridcloudworks.com",)}
    base.update(overrides)
    return Settings(**base)


def load_sample(name: str) -> Any:
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


def make_body(
    content: Any = None,
    decision: Any = None,
    *,
    kind: str = "arg-export",
    name: str | None = "sample-resource-graph.json",
) -> dict[str, Any]:
    """An upload request: the sample export and the zone-redundancy decision unless told otherwise."""
    file: dict[str, Any] = {
        "kind": kind,
        "content": content if content is not None else load_sample("sample-resource-graph.json"),
    }
    if name:
        file["name"] = name
    return {
        "evidence": [file],
        "decision": decision if decision is not None else load_sample("decision-zone-redundancy.json"),
    }


def one_claim_decision(**claim: Any) -> dict[str, Any]:
    """The smallest valid decision: one region claim, with any field of the claim replaced by a keyword."""
    base = {
        "statement": "s",
        "detectorId": "region-allowed",
        "expectation": {"property": "location", "operator": "in", "value": ["centralus"]},
    }
    return {"title": "t", "claims": [{**base, **claim}]}


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def sample_export() -> dict[str, Any]:
    return load_sample("sample-resource-graph.json")


@pytest.fixture
def anyio_backend():
    return "asyncio"
