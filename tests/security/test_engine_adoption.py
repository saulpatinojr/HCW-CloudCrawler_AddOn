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
from packaging.version import Version

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
    """Requirement lines in a form that does not depend on how a tool ordered or spaced them. The extras and a URL are
    part of what is compared: the image installs the lock with `pip --no-deps`, so `pydantic[email]` and `pydantic` are
    different locks, and a requirement that names a URL is a different file."""
    found = []
    for line in lines:
        requirement = Requirement(line)
        found.append(
            (
                canonicalize_name(requirement.name),
                tuple(sorted(canonicalize_name(extra) for extra in requirement.extras)),
                str(requirement.specifier),
                requirement.url,
                str(requirement.marker),
            )
        )
    return sorted(found, key=repr)


def _extras(values):
    """Extras names as a set, in their normalised spelling."""
    return {canonicalize_name(value) for value in values or []}


# Every 3.X.Y from 3.0.0 to 3.40.99. packaging cannot say "this range lies inside that range", and a Requires-Python can
# exclude a single patch release (`!=3.14.7`) or stop at one (`<3.14.9`), so checking only the two ends of the project
# range would miss those. Testing each version the project range allows is simple and cannot be wrong for a range that
# lies inside the grid; _python_versions_missing refuses a project range that reaches the grid's top.
PYTHON_VERSIONS = [Version(f"3.{minor}.{patch}") for minor in range(41) for patch in range(100)]


def _python_versions_missing(engine_range, project_range):
    """The Python versions the project range allows and the engine's Requires-Python does not."""
    engine, project = SpecifierSet(engine_range or ""), SpecifierSet(project_range)
    assert PYTHON_VERSIONS[-1] not in project, "the project's requires-python reaches past the versions this test tries"
    return [str(version) for version in PYTHON_VERSIONS if version in project and version not in engine]


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


def _bump_step(workflow):
    """The step of core-update.yml that rewrites the pin and re-locks: from its name to the next step."""
    start = workflow.index("name: Bump CORE_REF and re-lock")
    following = re.search(r"(?m)^      - ", workflow[start:])
    return workflow[start : start + following.start()] if following else workflow[start:]


def test_core_update_moves_the_static_metadata_before_it_locks():
    """Inside the bump step only: the file's header comment also says CORE_METADATA, so a search of the whole file
    would pass even if the `sed` and its `grep` were deleted or moved after `uv lock`."""
    step = _bump_step((ROOT / ".github" / "workflows" / "core-update.yml").read_text(encoding="utf-8"))
    moved = re.search(r'(?m)^\s*sed -i -E ".*CORE_METADATA.*" pyproject\.toml\s*$', step)
    checked = re.search(r'(?m)^\s*grep -qE ".*CORE_METADATA.*" pyproject\.toml\s*$', step)
    locked = step.find("uv lock --upgrade-package cloud-crawler-core")
    assert moved and checked and locked >= 0, "the bump step must sed the CORE_METADATA version, grep it, then lock"
    assert moved.start() < checked.start() < locked, "the version must be changed and checked before `uv lock` runs"


def test_lock_manifest_records_the_same_static_metadata():
    """`uv lock --check` (ci.yml) already refuses a lock that disagrees with pyproject.toml; this names the reason."""
    wanted = _static_metadata(_pyproject()).get(ENGINE)
    recorded = {canonicalize_name(e["name"]): e for e in _lock().get("manifest", {}).get("dependency-metadata", [])}
    entry = recorded.get(ENGINE)
    assert wanted and entry, "uv.lock must record the engine's static metadata (run `uv lock`)"
    assert entry["version"] == wanted["version"]
    assert _requirements(entry["requires-dist"]) == _requirements(wanted["requires-dist"])
    assert _extras(entry.get("provides-extra")) == _extras(wanted.get("provides-extra"))


def test_static_metadata_does_not_set_requires_python():
    """Dependabot copies the first `requires-python` in uv.lock over every other one (dependabot-core,
    lock_file_updater.rb), so a different range in this entry would make the lock of every Dependabot pull request fail
    `uv lock --check`. The project's own range already limits where the engine can be installed."""
    assert "requires-python" not in _static_metadata(_pyproject())[ENGINE]


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
    differing = _entry_differences(entry, wheel["Version"], metadata.requires(ENGINE), wheel.get_all("Provides-Extra"))
    assert not differing, f"the entry differs from the installed wheel in: {', '.join(differing)}"


def _entry_differences(entry, wheel_version, wheel_requires, wheel_extras):
    """Which of the entry's fields differ from what a wheel says. Extras are compared, not forbidden: a release that
    gains an extra passes once the entry lists the same extra (`provides-extra`) and its requirements."""
    found = []
    if wheel_version != entry["version"]:
        found.append("version")
    if _requirements(wheel_requires or []) != _requirements(entry["requires-dist"]):
        found.append("requires-dist")
    if _extras(wheel_extras) != _extras(entry.get("provides-extra")):
        found.append("provides-extra")
    return found


ADAPTED_ENTRY = {
    "version": "0.2.0",
    "requires-dist": ["pydantic>=2.14,<3", "email-validator>=2 ; extra == 'email'"],
    "provides-extra": ["email"],
}
ADAPTED_REQUIRES = ["pydantic<3,>=2.14", 'email-validator>=2; extra == "email"']


def test_entry_comparison_passes_a_correctly_adapted_bump_that_gains_an_extra():
    assert _entry_differences(ADAPTED_ENTRY, "0.2.0", ADAPTED_REQUIRES, ["email"]) == []


@pytest.mark.parametrize(
    ("entry_change", "wheel_version", "wheel_requires", "wheel_extras", "expected"),
    [
        ({}, "0.3.0", ADAPTED_REQUIRES, ["email"], ["version"]),
        ({"provides-extra": []}, "0.2.0", ADAPTED_REQUIRES, ["email"], ["provides-extra"]),
        ({"provides-extra": ["email", "toml"]}, "0.2.0", ADAPTED_REQUIRES, ["email"], ["provides-extra"]),
        ({}, "0.2.0", ADAPTED_REQUIRES[:1], ["email"], ["requires-dist"]),
        ({}, "0.2.0", ADAPTED_REQUIRES + ["orjson>=3"], ["email"], ["requires-dist"]),
        ({}, "0.2.0", ["pydantic[email]<3,>=2.14", ADAPTED_REQUIRES[1]], ["email"], ["requires-dist"]),
    ],
)
def test_entry_comparison_names_every_field_that_differs(
    entry_change, wheel_version, wheel_requires, wheel_extras, expected
):
    entry = {**ADAPTED_ENTRY, **entry_change}
    assert _entry_differences(entry, wheel_version, wheel_requires, wheel_extras) == expected


def test_wheel_accepts_every_python_the_project_allows():
    """The entry leaves requires-python out on purpose (Dependabot copies the first requires-python in uv.lock over
    every other one), so this is the only automatic check of the engine's Requires-Python. A release that narrows it,
    say to >=3.14.8 while the project still allows 3.14.6, fails the bump pull request's compatibility check. What to
    do then is a decision for a person: raise the project's requires-python, or do not adopt that release (runbook)."""
    project = _pyproject()["project"]["requires-python"]
    missing = _python_versions_missing(metadata.metadata(ENGINE).get("Requires-Python"), project)
    assert not missing, f"requires-python {project} allows Python {missing[0]}..{missing[-1]}, which the engine refuses"


@pytest.mark.parametrize(
    ("engine_range", "first_missing"),
    [
        (">=3.14.8", "3.14.6"),
        ("<3.14.9", "3.14.9"),
        ("!=3.14.7", "3.14.7"),
        (">=3.14.6,<3.14.12", "3.14.12"),
        (">=3.15", "3.14.6"),
    ],
)
def test_python_range_check_notices_a_narrower_engine(engine_range, first_missing):
    assert _python_versions_missing(engine_range, ">=3.14.6,<3.15")[0] == first_missing


@pytest.mark.parametrize("engine_range", ["<3.15,>=3.14.6", ">=3.14", ">=3.14.6,<3.16", "", None])
def test_python_range_check_accepts_the_same_or_a_wider_engine(engine_range):
    assert _python_versions_missing(engine_range, ">=3.14.6,<3.15") == []


def test_python_range_check_refuses_a_project_range_it_cannot_cover():
    with pytest.raises(AssertionError):
        _python_versions_missing(">=3.14", ">=3.14.6")


@pytest.mark.parametrize(
    "changed",
    ["pydantic [email]>=2.14,<3", "pydantic[email]>=2.14,<3", "pydantic @ https://example.invalid/p.whl", "orjson>=3"],
)
def test_requirement_comparison_notices_extras_urls_and_new_names(changed):
    assert _requirements([changed]) != _requirements(["pydantic>=2.14,<3"])


def test_requirement_comparison_ignores_order_spacing_and_name_spelling():
    assert _requirements(["Pydantic [ Email ] >= 2.14 , < 3", "idna>=3"]) == _requirements(
        ["idna>=3", "pydantic[email]<3,>=2.14"]
    )


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


def _requires_only_plain_pydantic(lines):
    """True when the requirement lines are exactly one `pydantic`, with no extras and no URL. The lines are parsed, not
    split at the first space or operator, so `pydantic [email]>=2` is not mistaken for `pydantic`."""
    parsed = [Requirement(line) for line in lines or []]
    return [(canonicalize_name(r.name), set(r.extras), r.url) for r in parsed] == [("pydantic", set(), None)]


def test_engine_requires_only_pydantic():
    assert _requires_only_plain_pydantic(metadata.requires(ENGINE))


@pytest.mark.parametrize(
    "lines",
    [
        ["pydantic [email]>=2.14,<3"],
        ["pydantic[email]>=2.14,<3"],
        ["pydantic @ https://example.invalid/p.whl"],
        ["pydantic>=2.14,<3", "orjson>=3"],
        ["orjson>=3"],
        [],
    ],
)
def test_only_pydantic_check_rejects_extras_urls_other_packages_and_none(lines):
    assert not _requires_only_plain_pydantic(lines)


def test_only_pydantic_check_accepts_the_wheels_spelling():
    assert _requires_only_plain_pydantic(["pydantic<3,>=2.14"])


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
