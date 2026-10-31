"""core-update.yml refuses an upstream release tag, or a pinned CORE_REF, that is not a plain vMAJOR.MINOR.PATCH.

Both values go into GITHUB_OUTPUT, a URL and the bump script's arguments, so a tag with shell metacharacters or a line
break must stop the run before it is used. Both jobs read the tags themselves (the bump job's `refs` step and the
pull-request job's `expect` step, which does not trust the bump job), so both carry the guard. These tests run the
guard's own lines from the workflow with bash, so they fail if the guard is removed, loosened or moved after the first
use.
"""

import re
import shutil
import subprocess

import pytest

from ..conftest import ROOT

TEXT = (ROOT / ".github" / "workflows" / "core-update.yml").read_text(encoding="utf-8")
STEPS = re.split(r"(?m)^ {6}- ", TEXT.split("\njobs:\n", 1)[1])[1:]
STEP_IDS = ["refs", "expect"]  # the bump job's and the pull-request job's
needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash is not installed")
HOSTILE = [
    "v9|;etouch${IFS}PWNED;#",
    "v1.0.0\nchanged=true",
    "v1.0.0\r",
    "v1.2.3+build.7",
    "v1.2.3-rc.1",
    "v1.0",
    "1.2.3",
    "latest",
    "",
]
HOSTILE_IDS = [
    "sed-e-command",
    "newline",
    "carriage-return",
    "build-metadata",
    "pre-release",
    "two-parts",
    "no-v",
    "word",
    "empty",
]


def _script(step_id: str) -> str:
    found = [
        s for s in STEPS if re.match(rf"id:\s*{step_id}\s*$", s.splitlines()[0]) or f"\n        id: {step_id}\n" in s
    ]
    assert len(found) == 1, f"core-update.yml must have exactly one step with id: {step_id}"
    script = found[0].split("run: |\n", 1)[1]
    return "\n".join(line[10:] for line in script.splitlines())


def _guard(step_id: str) -> str:
    """From the single-line check to the last shape check, as written."""
    lines = _script(step_id).splitlines()
    start = next(i for i, line in enumerate(lines) if line.lstrip().startswith('case "$latest" in'))
    shapes = [i for i, line in enumerate(lines) if "=~" in line]
    assert shapes and start < shapes[0], "the single-line check must come before the shape checks"
    assert any("$latest" in lines[i] for i in shapes) and any("$current" in lines[i] for i in shapes)
    return "\n".join(lines[start : shapes[-1] + 1])


def _run(step_id: str, latest: str, current: str = "v0.1.0") -> subprocess.CompletedProcess:
    env = {"latest": latest, "current": current, "PATH": "/usr/bin:/bin"}
    return subprocess.run(["bash", "-c", _guard(step_id), "_"], env=env, capture_output=True, text=True)


@pytest.mark.parametrize("step_id", STEP_IDS)
def test_the_guard_runs_before_latest_or_current_is_written_or_used(step_id):
    script = _script(step_id)
    written = script.index('echo "latest=$latest"')
    assert script.index('case "$latest" in') < written, "the tag reaches GITHUB_OUTPUT before it is checked"
    for name in ("latest", "current"):
        shape = re.search(rf'\[\[ "\${name}" =~ \^v\[0-9\]\+\\\.\[0-9\]\+\\\.\[0-9\]\+\$ \]\]', script)
        assert shape and shape.start() < written, f"${name} must be checked as vMAJOR.MINOR.PATCH before any output"
    assert "bump_core_pin.py" not in script[:written], "nothing may use the tags before they are checked"


@needs_bash
@pytest.mark.parametrize("step_id", STEP_IDS)
@pytest.mark.parametrize("tag", ["v0.1.0", "v1.2.3", "v10.20.30"])
def test_a_plain_release_tag_passes(step_id, tag):
    result = _run(step_id, tag)
    assert result.returncode == 0, result.stdout + result.stderr


@needs_bash
@pytest.mark.parametrize("step_id", STEP_IDS)
@pytest.mark.parametrize("tag", HOSTILE, ids=HOSTILE_IDS)
def test_anything_else_stops_the_run(step_id, tag):
    result = _run(step_id, tag)
    assert result.returncode != 0
    assert "::error::" in result.stdout


@needs_bash
@pytest.mark.parametrize("step_id", STEP_IDS)
@pytest.mark.parametrize(
    "current", [t for t in HOSTILE if t], ids=[i for t, i in zip(HOSTILE, HOSTILE_IDS, strict=True) if t]
)
def test_a_pinned_core_ref_of_another_shape_stops_the_run(step_id, current):
    result = _run(step_id, "v9.9.9", current=current)
    assert result.returncode != 0
    assert "::error::" in result.stdout
