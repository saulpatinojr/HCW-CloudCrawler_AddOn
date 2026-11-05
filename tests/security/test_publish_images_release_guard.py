"""`publish-images.yml` runs `scripts/check_release_version.py` before it builds anything, tag run and dry run alike.

A `v*` tag publishes the image and cannot be taken back. The guard refuses a tag that disagrees with the version in the
code, a changelog with no dated section for the version, entries still under `[Unreleased]`, or a commit that is not on
`main`. The dry run (a manual run of the workflow) must refuse exactly the same states, with `--rehearse`, or a green
dry run proves nothing about the tag: a sister repository burned a tag that way on 2026-11-04. These tests pin the step
down: it exists once, it runs before the build, it uses `--tag` on a tag and `--rehearse` otherwise, both with
`--ancestor-of origin/main`, and the checkout fetches the history that `--ancestor-of` needs. The `lint` job of `ci.yml`
runs the no-tag mode on every pull request, so the version places can never drift between releases.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
SCRIPT = "scripts/check_release_version.py"


def _code(name: str) -> str:
    text = (WORKFLOWS / name).read_text(encoding="utf-8").replace("\r\n", "\n")
    # Comment lines are removed before anything is matched, so a comment can never satisfy an assertion.
    return "\n".join(line for line in text.split("\n") if not line.lstrip().startswith("#"))


def _steps(name: str, job: str) -> list[str]:
    code = _code(name)
    jobs = dict(re.findall(r"(?ms)^  ([a-z-]+):\n(.*?)(?=^  [a-z-]+:\n|\Z)", code.split("\njobs:\n", 1)[1]))
    return re.split(r"(?m)^ {6}- ", jobs[job])[1:]


PUBLISH = _steps("publish-images.yml", "build-scan-publish")
GUARD = [s for s in PUBLISH if SCRIPT in s]


def test_the_publish_workflow_runs_the_guard_exactly_once_before_the_build():
    assert len(GUARD) == 1, f"publish-images.yml must run {SCRIPT} in exactly one step"
    guard_index = PUBLISH.index(GUARD[0])
    build_index = next(i for i, s in enumerate(PUBLISH) if "docker/build-push-action@" in s)
    version_index = next(i for i, s in enumerate(PUBLISH) if s.startswith("id: version"))
    assert guard_index < version_index < build_index, "the guard runs before the version step and the build"


def test_a_tag_runs_tag_mode_and_a_manual_run_rehearses_with_the_same_ancestry_check():
    step = GUARD[0]
    assert 'if [ "$REF_TYPE" = "tag" ]; then mode=(--tag "$REF_NAME"); else mode=(--rehearse); fi' in step
    assert f'python {SCRIPT} "${{mode[@]}}" --ancestor-of origin/main' in step
    assert 'REF_TYPE: "${{ github.ref_type }}"' in step and 'REF_NAME: "${{ github.ref_name }}"' in step
    assert "set -euo pipefail" in step
    assert not re.search(rf"python {re.escape(SCRIPT)}\s*$", step, re.M), "no bare version-only call in the publish job"
    assert "continue-on-error" not in step and "\nif:" not in step


def test_the_checkout_fetches_the_history_the_ancestry_check_needs_and_keeps_no_credentials():
    checkout = next(s for s in PUBLISH if s.startswith("uses: actions/checkout@"))
    assert "fetch-depth: 0" in checkout, "--ancestor-of origin/main needs the branch history, not a shallow clone"
    assert "persist-credentials: false" in checkout


def test_the_ci_lint_job_runs_the_no_tag_mode_on_every_pull_request():
    steps = [s for s in _steps("ci.yml", "lint") if SCRIPT in s]
    assert len(steps) == 1
    assert re.search(rf"run: uv run python {re.escape(SCRIPT)}\s*$", steps[0], re.M)
    assert "--tag" not in steps[0] and "--rehearse" not in steps[0]


def test_make_lint_runs_the_same_check():
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8").replace("\r\n", "\n")
    lint = makefile.split("\nlint:\n", 1)[1].split("\n\n", 1)[0]
    assert f"\tuv run python {SCRIPT}" in lint
