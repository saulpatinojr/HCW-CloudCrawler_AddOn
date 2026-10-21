"""The lab edition is technically unable to reach Azure (AddOn Integration Standard, section 19; ADR 0001)."""

import ast
import re
import subprocess
import sys

import pytest

from ..conftest import ROOT

FORBIDDEN_ENDPOINTS = ("management.azure.com", "login.microsoftonline.com", "graph.microsoft.com")
FORBIDDEN_MODULES = ("azure", "msal", "boto3", "botocore", "msrest")
PY_DIRS = [ROOT / "src", ROOT / "tests"]


def _py_files():
    for base in PY_DIRS:
        yield from (p for p in base.rglob("*.py") if ".venv" not in p.parts)


def test_no_cloud_sdk_in_dependency_manifests():
    for name in ("pyproject.toml", "uv.lock"):
        text = (ROOT / name).read_text(encoding="utf-8")
        for pkg in ("azure-", "msal", "msrest", "boto3", "botocore"):
            assert not re.search(rf'name = "{pkg}', text), f"{name} depends on {pkg}"
            assert not re.search(rf"^{pkg}[\w-]*==", text, re.MULTILINE), f"{name} pins {pkg}"


def test_no_cloud_sdk_imports_anywhere():
    for path in _py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                assert name.split(".")[0] not in FORBIDDEN_MODULES, f"{path} imports {name}"


def test_no_azure_endpoints_in_code_or_pane():
    for base in [ROOT / "src", ROOT / "web"]:
        for path in base.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".js", ".html", ".css", ".json"} and ".venv" not in path.parts:
                text = path.read_text(encoding="utf-8", errors="ignore")
                for endpoint in FORBIDDEN_ENDPOINTS:
                    assert endpoint not in text, f"{path} references {endpoint}"


def test_guard_refuses_identity_endpoint_in_a_fresh_process():
    proc = subprocess.run(
        [sys.executable, "-c", "import cloud_crawler_lab.app"],
        env={
            "PATH": "/usr/bin:/bin",
            "IDENTITY_ENDPOINT": "http://169.254.169.254/metadata/identity",
            "PYTHONPATH": ":".join(sys.path),
        },
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode != 0


def test_cloud_sdks_not_importable_in_this_environment():
    for module in ("azure", "msal", "boto3"):
        with pytest.raises(ImportError):
            __import__(module)


def test_pane_has_no_credential_inputs():
    for path in (ROOT / "web").glob("*"):
        text = path.read_text(encoding="utf-8")
        assert 'type="password"' not in text and "type='password'" not in text, path
        assert "<input" not in text or 'type="file"' in text, "the only input is the file picker"
    assert "never asks for credentials" in (ROOT / "web" / "index.html").read_text(encoding="utf-8")


def test_pane_has_no_sign_in_and_no_token_handling():
    for path in (ROOT / "web").glob("*.js"):
        text = path.read_text(encoding="utf-8").lower()
        for word in ("authorization", "bearer", "msal", "oauth", "localstorage", "sessionstorage"):
            assert word not in text, f"{path.name} mentions {word}"


def test_dockerfile_and_compose_have_no_azure():
    """Outside comments, the only `azure` in the Dockerfile is the boundary guard's forbidden list."""
    for name in ("infrastructure/docker/Dockerfile", "docker-compose.yml"):
        for line in (ROOT / name).read_text(encoding="utf-8").splitlines():
            code = line.split("#", 1)[0].lower()
            if "azure" in code or "msal" in code or "boto3" in code:
                assert "forbidden" in code or "edition boundary" in code, f"{name}: {line.strip()}"
            assert "pip install" not in code or "requirements.lock.txt" in code, f"{name}: {line.strip()}"
            assert "identity_endpoint=" not in code and "msi_endpoint=" not in code, f"{name}: {line.strip()}"


def test_health_reports_disabled_by_design(client):
    assert client.get("/api/health").json()["azureConnectivity"] == "disabled-by-design"


def test_no_route_can_call_azure(client):
    """Every documented route is read-only and local; nothing in the application reaches out."""
    from cloud_crawler_lab.app import api_routes

    assert api_routes(client.app) == {"/api/health": {"GET"}}
    outbound = ("urllib", "httpx", "requests", "aiohttp", "http")
    for path in (ROOT / "src").rglob("*.py"):
        if path.name == "turnstile.py":
            continue  # the one outbound call: human verification, to a fixed https endpoint, never to a cloud
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                assert name.split(".")[0] not in outbound, f"{path} imports {name}"
