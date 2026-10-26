"""The engine (`cloud-crawler-core`) is adopted from the App's release wheel, pinned by URL and hash, and inside the
edition boundary (ADR 0001). These tests hold the pin, the lock and the engine's own imports."""

import ast
import re
from importlib import metadata
from pathlib import Path

import cloud_crawler_core
import pytest

from cloud_crawler_lab.security import redaction as lab_redaction

from ..conftest import ROOT

FORBIDDEN_MODULES = ("azure", "msal", "boto3", "botocore", "msrest")
OUTBOUND_MODULES = (
    "urllib",
    "httpx",
    "requests",
    "aiohttp",
    "http",
    "socket",
    "ssl",
    "subprocess",
    "ftplib",
    "smtplib",
)
UPSTREAM_RELEASES = "https://github.com/saulpatinojr/HCW-CloudCrawler_App/releases/download/"

PIN = re.compile(
    r'^\s*"cloud-crawler-core @ (?P<url>' + re.escape(UPSTREAM_RELEASES) + r"(?P<tag>v[0-9][0-9A-Za-z.+-]*)/"
    r'cloud_crawler_core-(?P<ver>[0-9][0-9A-Za-z.+-]*)-py3-none-any\.whl)",\s*#\s*CORE_REF\s+(?P<ref>v\S+)\s*$',
    re.MULTILINE,
)


def _pin():
    match = PIN.search((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert match, "pyproject.toml must carry the one-line CORE_REF pin that core-update.yml rewrites"
    return match


def test_pin_line_has_the_shape_core_update_rewrites():
    pin = _pin()
    assert pin["tag"] == pin["ref"] and pin["ver"] == pin["tag"].removeprefix("v")


def test_installed_engine_is_the_pinned_release():
    assert metadata.version("cloud-crawler-core") == _pin()["ver"]


def test_lock_records_the_wheel_url_and_a_sha256():
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
    block = re.search(
        r'\[\[package\]\]\nname = "cloud-crawler-core"\n(?P<body>.*?)\n\[package\.metadata\]', lock, re.DOTALL
    )
    assert block, "uv.lock has no cloud-crawler-core entry"
    assert f'url = "{_pin()["url"]}"' in block["body"]
    assert re.search(r'hash = "sha256:[0-9a-f]{64}"', block["body"]), "the wheel's sha256 must be in the lock"


def test_engine_is_not_a_second_source_of_cloud_access():
    """Walk the installed engine: it imports no cloud SDK and nothing that can open a connection."""
    root = Path(cloud_crawler_core.__file__).parent
    files = list(root.rglob("*.py"))
    assert files, "engine sources not found"
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                top = name.split(".")[0]
                assert top not in FORBIDDEN_MODULES, f"{path.name} imports {name}"
                assert top not in OUTBOUND_MODULES, f"{path.name} imports {name}"


def test_engine_requires_only_pydantic():
    requirements = metadata.requires("cloud-crawler-core") or []
    assert [re.split(r"[<>=!~ ;]", r, maxsplit=1)[0] for r in requirements] == ["pydantic"]


def test_lab_only_words_are_not_in_the_engine_list():
    """A word the engine gains later must leave the lab's own list, so the lab never shadows the engine's rules."""
    assert not (lab_redaction.LAB_ONLY_WORDS & lab_redaction.ENGINE_ALLOWED_WORDS)
    assert lab_redaction.ALLOWED_WORDS == lab_redaction.ENGINE_ALLOWED_WORDS | lab_redaction.LAB_ONLY_WORDS


def test_guard_allows_lab_words_and_keeps_every_engine_rule():
    lab_redaction.assert_no_visitor_data({"event": "turnstile_disabled", "warning": True, "n": 3, "x": None})
    lab_redaction.assert_no_visitor_data({"event": "startup", "format": "arg-json"})
    with pytest.raises(lab_redaction.VisitorDataError):
        lab_redaction.assert_no_visitor_data({"event": "startup", "name": "hcw-sample-aks"})
    with pytest.raises(lab_redaction.VisitorDataError):
        lab_redaction.assert_no_visitor_data({"not an identifier": 1})
    with pytest.raises(lab_redaction.VisitorDataError):
        lab_redaction.assert_no_visitor_data({"event": "session_opened", "not an identifier": 1})


def test_scrub_is_the_engines():
    from cloud_crawler_core import redaction as engine

    assert lab_redaction.scrub is engine.scrub and lab_redaction.VisitorDataError is engine.VisitorDataError
