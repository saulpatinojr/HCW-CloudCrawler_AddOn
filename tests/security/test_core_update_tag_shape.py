"""The core-update workflow refuses an upstream release tag that is not a plain vMAJOR.MINOR.PATCH.

The tag is pasted into a sed command and into GITHUB_OUTPUT, in the job that later mints the App token, so a tag with
shell or sed metacharacters, or a line break, must stop the run before it is used. These tests run the guard's own
lines from the workflow with bash, so they fail if the guard is removed, loosened or moved after the first use.
"""

import re
import shutil
import subprocess

import pytest

from ..conftest import ROOT

TEXT = (ROOT / ".github" / "workflows" / "core-update.yml").read_text(encoding="utf-8")
STEPS = re.split(r"(?m)^ {6}- ", TEXT.split("\njobs:\n", 1)[1])[1:]
needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash is not installed")


def _refs_script() -> str:
    found = [s for s in STEPS if re.match(r"id:\s*refs\s*$", s.splitlines()[0])]
    assert len(found) == 1, "core-update.yml must have exactly one step with id: refs"
    script = found[0].split("run: |\n", 1)[1]
    return "\n".join(line[10:] for line in script.splitlines())


def _guard() -> str:
    lines = _refs_script().splitlines()
    start = next(i for i, line in enumerate(lines) if line.lstrip().startswith('case "$latest" in'))
    end = next(i for i, line in enumerate(lines) if "=~" in line and "$latest" in line)
    assert start < end, "the single-line check must come before the shape check"
    return "\n".join(lines[start : end + 1])


def test_the_guard_runs_before_latest_is_written_or_used():
    script = _refs_script()
    guard_at = script.index('case "$latest" in')
    assert guard_at < script.index('echo "latest=$latest"'), "the tag reaches GITHUB_OUTPUT before it is checked"


@needs_bash
@pytest.mark.parametrize("tag", ["v0.1.0", "v1.2.3", "v10.20.30"])
def test_a_plain_release_tag_passes(tag):
    result = subprocess.run(["bash", "-c", _guard(), "_"], env={"latest": tag}, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


@needs_bash
@pytest.mark.parametrize(
    "tag",
    [
        "v9|;etouch${IFS}PWNED;#",
        "v1.0.0\nchanged=true",
        "v1.0.0\r",
        "v1.2.3+build.7",
        "v1.2.3-rc.1",
        "v1.0",
        "1.2.3",
        "latest",
        "",
    ],
    ids=[
        "sed-e-command",
        "newline",
        "carriage-return",
        "build-metadata",
        "pre-release",
        "two-parts",
        "no-v",
        "word",
        "empty",
    ],
)
def test_anything_else_stops_the_run(tag):
    result = subprocess.run(["bash", "-c", _guard(), "_"], env={"latest": tag}, capture_output=True, text=True)
    assert result.returncode != 0
    assert "::error::" in result.stdout
