"""The engine (`cloud-crawler-core`) is adopted from the App's release wheel, pinned by URL and hash, and inside the
edition boundary (ADR 0001). These tests hold the pin, the lock and the engine's own imports."""

import ast
import re
import tomllib
from importlib import metadata
from pathlib import Path

import cloud_crawler_core
import pytest
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name

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


ENGINE = "cloud-crawler-core"
METADATA_MARKER = re.compile(r'^version = "(?P<ver>[^"]+)"[ \t]*#[ \t]*CORE_METADATA[ \t]*$', re.MULTILINE)


def _static_metadata(document):
    """The `[[tool.uv.dependency-metadata]]` entries of a parsed pyproject.toml, by package name."""
    entries = document.get("tool", {}).get("uv", {}).get("dependency-metadata", [])
    return {canonicalize_name(entry["name"]): entry for entry in entries}


def _lock():
    return tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))


def _pyproject():
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _requirements(lines):
    """Requirement lines in a form that does not depend on how a tool ordered or spaced them."""
    found = []
    for line in lines:
        requirement = Requirement(line)
        found.append((canonicalize_name(requirement.name), str(requirement.specifier), str(requirement.marker)))
    return sorted(found)


def test_engine_has_static_metadata_for_the_pinned_wheel():
    """Without it uv asks the wheel's address for the wheel's metadata every time it re-resolves the lock, and
    Dependabot's uv job fails on that request for every package (issue 33). It must be the pinned version's."""
    entry = _static_metadata(_pyproject()).get(ENGINE)
    assert entry, "pyproject.toml needs a [[tool.uv.dependency-metadata]] entry for cloud-crawler-core"
    assert entry.get("version") == _pin()["ver"]
    assert entry.get("requires-dist"), "the entry must list the engine's dependencies (copy them from the wheel)"


def test_static_metadata_carries_the_marker_core_update_moves():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    found = METADATA_MARKER.findall(text)
    assert found == [_pin()["ver"]], "exactly one `version = ...  # CORE_METADATA` line, equal to the pinned version"


def test_core_update_moves_the_static_metadata_before_it_locks():
    workflow = (ROOT / ".github" / "workflows" / "core-update.yml").read_text(encoding="utf-8")
    moved = workflow.find("CORE_METADATA")
    locked = workflow.find("uv lock --upgrade-package cloud-crawler-core")
    assert 0 <= moved < locked, "the bump must change the metadata version before `uv lock` runs"


def test_lock_manifest_records_the_same_static_metadata():
    """`uv lock --check` (ci.yml) already refuses a lock that disagrees with pyproject.toml; this names the reason."""
    wanted = _static_metadata(_pyproject()).get(ENGINE)
    recorded = {canonicalize_name(e["name"]): e for e in _lock().get("manifest", {}).get("dependency-metadata", [])}
    entry = recorded.get(ENGINE)
    assert wanted and entry, "uv.lock must record the engine's static metadata (run `uv lock`)"
    assert entry["version"] == wanted["version"]
    assert _requirements(entry["requires-dist"]) == _requirements(wanted["requires-dist"])
    assert SpecifierSet(entry.get("requires-python", "")) == SpecifierSet(wanted.get("requires-python", ""))


def test_every_direct_url_package_in_the_lock_has_static_metadata():
    """The break this guards: a package pinned by URL with no static metadata makes uv fetch from that URL on every
    re-resolve, and Dependabot's uv job reports the failed request as a private source. Any future URL pin (another
    engine, a second wheel) must come with its metadata."""
    given = _static_metadata(_pyproject())
    urls = [
        (canonicalize_name(p["name"]), p["version"])
        for p in _lock()["package"]
        if isinstance(p.get("source"), dict) and "url" in p["source"]
    ]
    assert (canonicalize_name(ENGINE), _pin()["ver"]) in urls, "the engine is expected to be a direct URL package"
    for name, version in urls:
        assert name in given and given[name].get("version") == version, f"{name} {version} has no static metadata"


def test_static_metadata_matches_the_installed_wheel():
    """The metadata is a copy. This compares it with the wheel that is really installed, so an upstream release that
    changes the engine's dependencies fails the bump pull request's compatibility check instead of shipping a lock
    that does not list them."""
    entry = _static_metadata(_pyproject())[ENGINE]
    wheel = metadata.metadata(ENGINE)
    assert wheel["Version"] == entry["version"]
    assert _requirements(metadata.requires(ENGINE) or []) == _requirements(entry["requires-dist"])
    assert SpecifierSet(wheel["Requires-Python"]) == SpecifierSet(entry["requires-python"])
    assert not wheel.get_all("Provides-Extra"), "the entry lists no extras; add provides-extra if the wheel gains any"


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
