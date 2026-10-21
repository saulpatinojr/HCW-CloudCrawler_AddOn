from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cloud_crawler_lab.app import create_app
from cloud_crawler_lab.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def make_settings(**overrides) -> Settings:
    base = {"allow_no_turnstile": True, "log_silent": True, "site_origins": ("https://hybridcloudworks.com",)}
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def anyio_backend():
    return "asyncio"
