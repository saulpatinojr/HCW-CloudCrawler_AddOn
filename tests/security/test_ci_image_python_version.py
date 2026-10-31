"""The `image` job in ci.yml checks that the built image runs the Python that versions.env names.

The `lint` job proves every FROM line is BASE_IMAGE@BASE_DIGEST, but a digest is only a checksum: nothing in the text
says which Python it carries. The step "The image runs the Python that versions.env names (BASE_PYTHON_VERSION)" asks
the built image (`python --version`) and fails when the answer differs from BASE_PYTHON_VERSION. These tests make sure
the step stays in the job, after the build and against the image the build tagged, and they run its script with a small
stand-in for `docker` so its pass and fail paths are tested without building anything.
"""

import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# Computed from this file's place, not imported from conftest, so the file is the same in every add-on repository.
ROOT = Path(__file__).resolve().parents[2]
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8").replace("\r\n", "\n")
# Comment lines are removed before anything is matched, so a comment can never satisfy an assertion.
CODE = "\n".join(line for line in CI.split("\n") if not line.lstrip().startswith("#"))
JOBS = dict(re.findall(r"(?ms)^  ([a-z-]+):\n(.*?)(?=^  [a-z-]+:\n|\Z)", CODE.split("\njobs:\n", 1)[1]))
STEP_NAME = "The image runs the Python that versions.env names (BASE_PYTHON_VERSION)"
OWN_VERSION = re.search(
    r"(?m)^BASE_PYTHON_VERSION=(.*)$",
    (ROOT / "infrastructure" / "docker" / "versions.env").read_text(encoding="utf-8").replace("\r\n", "\n"),
).group(1)


def _steps(job: str) -> list[str]:
    return re.split(r"(?m)^ {6}- ", JOBS[job])[1:]


def _run_body(step: str) -> str:
    lines = step.split("\n")
    for index, line in enumerate(lines):
        match = re.match(r"^(\s*)run:\s*\|\s*$", line)
        if match:
            indent = len(match.group(1))
            block = []
            for follower in lines[index + 1 :]:
                if follower.strip() and len(follower) - len(follower.lstrip()) <= indent:
                    break
                block.append(follower)
            return textwrap.dedent("\n".join(block))
    raise AssertionError("the step has no `run: |` block")


IMAGE_STEPS = _steps("image")
NAMED = [s for s in IMAGE_STEPS if re.match(rf"name:\s*{re.escape(STEP_NAME)}\s*$", s.split("\n", 1)[0])]


def test_the_image_job_has_the_python_version_step_once():
    assert len(NAMED) == 1, f"the image job must have exactly one step named {STEP_NAME!r}"


def test_the_step_comes_after_the_build_and_asks_the_image_the_build_tagged():
    build = [i for i, s in enumerate(IMAGE_STEPS) if "docker build " in s and "-t addon:ci " in s]
    assert len(build) == 1, "the image job builds addon:ci in exactly one step"
    assert IMAGE_STEPS.index(NAMED[0]) > build[0], "the check must run after the image is built"
    body = _run_body(NAMED[0])
    assert re.search(r"(?m)^set -euo pipefail$", body)
    assert "docker run --rm --entrypoint python addon:ci --version" in body
    assert "BASE_PYTHON_VERSION=" in body and "infrastructure/docker/versions.env" in body
    assert not re.search(r"(?m)^\s*if:", NAMED[0]), "the check runs on every build, with no condition"
    assert "continue-on-error" not in NAMED[0]


def _find_bash() -> str | None:
    if sys.platform == "win32":
        for candidate in (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe"):
            if Path(candidate).is_file():
                return candidate
        return None
    return shutil.which("bash")


BASH = _find_bash()
needs_bash = pytest.mark.skipif(BASH is None, reason="bash is not available on this computer")
DOCKER_STUB = """\
#!/usr/bin/env bash
# usage: docker run --rm --entrypoint python addon:ci --version; prints what the stand-in image's Python would
[ "$*" = "run --rm --entrypoint python addon:ci --version" ] || { echo "unexpected docker call: $*" >&2; exit 2; }
[ -n "$STUB_FAIL" ] && { echo "Unable to find image 'addon:ci' locally" >&2; exit 125; }
printf 'Python %s\\n' "$STUB_PYTHON"
"""


def _run(tmp_path: Path, image_python: str, versions_env: str | None = None, fail: bool = False):
    """Run the step's script with bash in a copy of the one file it reads, and `docker` replaced by the stand-in."""
    work = tmp_path / "repo"
    (work / "infrastructure" / "docker").mkdir(parents=True)
    env_text = (
        versions_env
        if versions_env is not None
        else (ROOT / "infrastructure/docker/versions.env").read_text(encoding="utf-8")
    )
    (work / "infrastructure" / "docker" / "versions.env").write_text(env_text, encoding="utf-8", newline="\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text(DOCKER_STUB, encoding="utf-8", newline="\n")
    (bin_dir / "docker").chmod(0o755)
    script = tmp_path / "step.sh"
    script.write_text(_run_body(NAMED[0]), encoding="utf-8", newline="\n")
    env = {
        **os.environ,
        "PATH": os.pathsep.join([bin_dir.as_posix(), os.environ.get("PATH", "")]),
        "STUB_PYTHON": image_python,
        "STUB_FAIL": "1" if fail else "",
    }
    assert BASH is not None
    result = subprocess.run(
        [BASH, "-e", script.as_posix()], cwd=work, env=env, capture_output=True, text=True, timeout=60
    )
    return result.returncode, result.stdout + result.stderr


@needs_bash
def test_the_step_passes_when_the_image_runs_the_named_python(tmp_path):
    code, log = _run(tmp_path, OWN_VERSION)
    assert code == 0, log
    assert OWN_VERSION in log


@needs_bash
@pytest.mark.parametrize("other", ["3.14.7", "3.14.80", "3.15.0"])
def test_the_step_fails_and_names_both_versions_when_the_image_runs_another_python(tmp_path, other):
    code, log = _run(tmp_path, other)
    assert code != 0
    assert "::error" in log
    assert f"Python {other}" in log and f"BASE_PYTHON_VERSION in versions.env is {OWN_VERSION}" in log


@needs_bash
def test_the_step_fails_when_the_image_cannot_be_run(tmp_path):
    code, log = _run(tmp_path, OWN_VERSION, fail=True)
    assert code != 0
    assert "could not run python --version" in log


@needs_bash
@pytest.mark.parametrize(
    "env_text",
    [
        "BASE_IMAGE=python:3.14.8-slim-trixie\n",
        "BASE_PYTHON_VERSION=3.14\n",
        "BASE_PYTHON_VERSION=3.14.8\nBASE_PYTHON_VERSION=3.14.9\n",
        "BASE_PYTHON_VERSION=3.14.8\nBASE_PYTHON_VERSION=\n",
        "BASE_PYTHON_VERSION=$(id)\n",
    ],
    ids=["missing", "not-major-minor-patch", "twice", "twice-second-empty", "not-a-version"],
)
def test_the_step_fails_on_a_versions_env_without_one_clean_version(tmp_path, env_text):
    code, log = _run(tmp_path, OWN_VERSION, versions_env=env_text)
    assert code != 0
    assert "BASE_PYTHON_VERSION must appear once as major.minor.patch" in log


@needs_bash
def test_a_windows_line_ending_in_versions_env_does_not_cause_a_false_failure(tmp_path):
    code, log = _run(tmp_path, "3.14.8", versions_env="BASE_PYTHON_VERSION=3.14.8\r\n")
    assert code == 0, log
