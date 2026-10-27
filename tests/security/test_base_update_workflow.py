"""base-update.yml opens its pull request with the HCW Main Admin GitHub App token, only when there is something to
move, and keeps untrusted text out of shell scripts.

The credential is the same one core-update.yml uses: the repository variable HCW_MAIN_ADMIN_CLIENT_ID and the repository
secret HCW_MAIN_ADMIN_PRIVATE_KEY, with no environment on the job. Most of these are static checks of the workflow text;
they do not prove the credential works or that a run opens a pull request. core-update.yml's probe run proves the
credential here, and the first real run (see docs/operations/runbook.md) proves the rest. The two `run:` scripts that
make decisions (the registry check and the choice of whether the second job has work) are also executed here against
stubbed `docker` and `gh` programs, because a regular expression over their text cannot show that they behave.
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
WORKFLOWS = ROOT / ".github" / "workflows"

TEXT = (WORKFLOWS / "base-update.yml").read_text(encoding="utf-8").replace("\r\n", "\n")
# Comment lines are removed before anything is matched, so a comment can never satisfy (or hide) an assertion.
CODE = "\n".join(line for line in TEXT.split("\n") if not line.lstrip().startswith("#"))
JOBS = dict(re.findall(r"(?ms)^  ([a-z-]+):\n(.*?)(?=^  [a-z-]+:\n|\Z)", CODE.split("\njobs:\n", 1)[1]))
PLAN_STEPS = re.split(r"(?m)^ {6}- ", JOBS["plan"])[1:]
OPEN_STEPS = re.split(r"(?m)^ {6}- ", JOBS["open-pr"])[1:]
APP_STEP_OUTPUT = r"\$\{\{\s*steps\.app-token\.outputs\.token\s*\}\}"
# The two files the script writes, spelled out here so a change to the script's constants is noticed by this test.
MOVED_FILES = ["infrastructure/docker/Dockerfile", "infrastructure/docker/versions.env"]


def _only(steps: list[str], action: str) -> str:
    found = [s for s in steps if re.search(rf"(?m)^\s*uses:\s*{re.escape(action)}@", s)]
    assert len(found) == 1, f"expected exactly one step using {action}"
    return found[0]


def _step_with_id(steps: list[str], step_id: str) -> str:
    found = [s for s in steps if re.search(rf"(?m)^\s*id:\s*{re.escape(step_id)}\s*$", s)]
    assert len(found) == 1, f"expected exactly one step with id {step_id}"
    return found[0]


def _run_bodies(text: str) -> list[str]:
    """Every `run:` value: a one-line value, or the lines of a block scalar (`|`, `|-`, `>`...)."""
    bodies: list[str] = []
    lines = text.split("\n")
    for index, line in enumerate(lines):
        match = re.match(r"^(\s*)(?:- )?run:\s*(.*)$", line)
        if not match:
            continue
        indent, rest = len(match.group(1)), match.group(2)
        if re.fullmatch(r"[|>][+-]?", rest):
            block = []
            for follower in lines[index + 1 :]:
                if follower.strip() and len(follower) - len(follower.lstrip()) <= indent:
                    break
                block.append(follower)
            bodies.append(textwrap.dedent("\n".join(block)))
        else:
            bodies.append(rest)
    return bodies


def test_there_are_two_jobs_and_only_the_second_holds_the_credential():
    assert set(JOBS) == {"plan", "open-pr"}
    assert not re.search(r"secrets\.|vars\.|create-github-app-token", JOBS["plan"]), "the plan job holds no credential"
    private_key = [line for line in CODE.split("\n") if "HCW_MAIN_ADMIN_PRIVATE_KEY" in line]
    assert len(private_key) == 1, "the private key must be named in exactly one place"
    with_key = [s for s in OPEN_STEPS if "secrets.HCW_MAIN_ADMIN_PRIVATE_KEY" in s]
    assert with_key == [_only(OPEN_STEPS, "actions/create-github-app-token")], "only the token step is given the key"


def test_no_job_runs_in_an_environment():
    # The credential is a repository variable and secret, so no environment is needed (or wanted) on any job.
    assert not re.search(r"(?m)^\s*environment:", TEXT)


def test_the_old_app_credential_and_environment_are_gone():
    for old in ("admin-ops", "APP_CLIENT_ID", "APP_PRIVATE_KEY"):
        assert old not in TEXT, f"{old} must not appear in base-update.yml"
    assert "portfolio" not in TEXT.lower(), "the Portfolio App must not appear in base-update.yml"


def test_workflow_reads_no_other_secrets():
    names = set(re.findall(r"secrets\.([A-Za-z0-9_]+)", TEXT))
    assert names == {"HCW_MAIN_ADMIN_PRIVATE_KEY"}
    for leak in ("toJSON(secrets", "secrets[", "secrets: inherit"):
        assert leak not in TEXT, f"{leak} would hand more than the one key to a step"


def test_the_workflow_runs_only_daily_and_by_hand_and_takes_no_input():
    """The whole `on:` block, so a second trigger (push, pull_request_target...) or an input cannot slip in."""
    block = re.search(r"(?ms)^on:\n(.*?)^permissions:", CODE)
    assert block is not None
    lines = [line for line in block.group(1).split("\n") if line.strip()]
    assert len(lines) == 2, f"expected only a schedule and workflow_dispatch, got: {lines}"
    assert re.fullmatch(r'  schedule: \[\{ cron: "\d{1,2} \d{1,2} \* \* \*" \}\]', lines[0])
    assert lines[1] == "  workflow_dispatch:"
    assert re.search(r"(?m)^concurrency: \{ group: base-update, cancel-in-progress: false \}$", CODE)


def test_second_job_runs_only_when_the_plan_decided_there_is_work():
    assert re.search(r"(?m)^ {4}needs:\s*plan\s*$", JOBS["open-pr"])
    assert re.search(r"(?m)^ {4}if:\s*needs\.plan\.outputs\.open_pr == 'true'\s*$", JOBS["open-pr"])
    registry = _step_with_id(PLAN_STEPS, "registry")
    assert re.search(r"(?m)^\s*if:\s*steps\.plan\.outputs\.changed == 'true'\s*$", registry)
    assert "linux/amd64" in registry and "comm -13" in registry, "the registry check must test the platforms"
    assert re.search(r"(?m)^\s*open_pr:\s*\$\{\{\s*steps\.pr\.outputs\.open_pr\s*\}\}\s*$", JOBS["plan"])


def test_pull_request_is_opened_with_the_app_token_never_github_token():
    app = _only(OPEN_STEPS, "actions/create-github-app-token")
    pr = _only(OPEN_STEPS, "peter-evans/create-pull-request")
    assert re.search(r"(?m)^\s*id:\s*app-token\s*$", app)
    assert OPEN_STEPS.index(app) < OPEN_STEPS.index(pr), "the App token step must come before the pull request step"
    assert re.search(rf"(?m)^\s*token:\s*{APP_STEP_OUTPUT}\s*$", pr)
    assert "GITHUB_TOKEN" not in pr and "github.token" not in pr, "create-pull-request must not be given GITHUB_TOKEN"
    apply_step = next(s for s in OPEN_STEPS if "follow_website_base.py" in s)
    assert OPEN_STEPS.index(apply_step) < OPEN_STEPS.index(app), "the files are edited before the credential is minted"


def test_app_credential_is_the_hcw_main_admin_variable_and_secret():
    app = _only(OPEN_STEPS, "actions/create-github-app-token")
    assert re.search(r"(?m)^\s*client-id:\s*\$\{\{\s*vars\.HCW_MAIN_ADMIN_CLIENT_ID\s*\}\}\s*$", app)
    assert re.search(r"(?m)^\s*private-key:\s*\$\{\{\s*secrets\.HCW_MAIN_ADMIN_PRIVATE_KEY\s*\}\}\s*$", app)


def test_app_token_is_limited_to_this_repository():
    app = _only(OPEN_STEPS, "actions/create-github-app-token")
    # With `owner` set and `repositories` empty the action mints a token for every repository of the installation.
    # With no `owner`, an empty `repositories` falls back to the current repository, so this shape fails closed.
    assert not re.search(r"(?m)^\s*owner:", app), "owner must not be set: an empty repositories would widen the token"
    # One value, this repository's full name: not a list, not a wildcard, not another repository.
    assert re.search(r"(?m)^\s*repositories:\s*\$\{\{\s*github\.repository\s*\}\}\s*$", app)


def test_app_token_permissions_are_exactly_contents_and_pull_requests_write():
    app = _only(OPEN_STEPS, "actions/create-github-app-token")
    granted = dict(re.findall(r"(?m)^\s*permission-([a-z-]+):\s*([a-z]+)\b", app))
    assert granted == {"contents": "write", "pull-requests": "write"}


def test_the_commit_is_credited_to_the_apps_bot_user_in_the_documented_form():
    bot = _step_with_id(OPEN_STEPS, "bot")
    assert OPEN_STEPS.index(_only(OPEN_STEPS, "actions/create-github-app-token")) < OPEN_STEPS.index(bot)
    assert '[[ "$id" =~ ^[0-9]+$ ]]' in bot, "the numeric id is checked before it is used"
    assert "@users.noreply.github.com" in bot and "+${APP_SLUG}[bot]" in bot, (
        "<id>+<slug>[bot]@users.noreply.github.com"
    )
    assert re.search(r"(?m)^\s*GH_TOKEN:\s*\$\{\{\s*github\.token\s*\}\}\s*$", bot), (
        "only a public lookup: no App token"
    )
    pr = _only(OPEN_STEPS, "peter-evans/create-pull-request")
    for key in ("author", "committer"):
        assert re.search(rf"(?m)^\s*{key}:\s*\$\{{\{{\s*steps\.bot\.outputs\.identity\s*\}}\}}\s*$", pr)


def test_the_pull_request_adds_exactly_the_two_files_the_script_writes_on_one_stable_branch():
    pr = _only(OPEN_STEPS, "peter-evans/create-pull-request")
    paths = re.search(r"(?ms)^\s*add-paths:\s*\|\n(.*?)(?=^\s*[a-z-]+:|\Z)", pr)
    assert paths is not None
    assert sorted(paths.group(1).split()) == MOVED_FILES
    assert re.search(r"(?m)^\s*branch:\s*base-update/website-base\s*$", pr), "one fixed branch, reused"
    assert not re.search(r"(?m)^\s*draft:\s*true", pr), "ready for review, never a draft"
    assert "auto-merge" not in CODE.lower() and "pr merge" not in CODE, "nothing is merged automatically"


def test_the_script_writes_only_the_files_the_pull_request_adds():
    script_text = (ROOT / "scripts" / "follow_website_base.py").read_text(encoding="utf-8")
    assert 'VERSIONS_ENV = Path("infrastructure/docker/versions.env")' in script_text
    assert 'DOCKERFILE = Path("infrastructure/docker/Dockerfile")' in script_text
    assert (ROOT / MOVED_FILES[0]).is_file() and (ROOT / MOVED_FILES[1]).is_file()


def test_the_pull_request_text_has_no_closing_keyword():
    """A pull request that says "fixes #N" closes that issue on merge; the automated pull request must never do so."""
    pr = _only(OPEN_STEPS, "peter-evans/create-pull-request")
    body = pr.split("body: |", 1)[1]
    assert not re.search(r"(?i)\b(close[sd]?|fix(e[sd])?|resolve[sd]?)\b[:\s]+\S*#\d+", body)


def test_a_box_in_the_pull_request_text_is_ticked_only_when_the_registry_comparison_ran():
    pr = _only(OPEN_STEPS, "peter-evans/create-pull-request")
    assert "[${{ needs.plan.outputs.compared == 'true' && 'x' || ' ' }}]" in pr
    assert "compared=${compared}" in _step_with_id(PLAN_STEPS, "registry")


def test_an_obsolete_pull_request_is_closed_by_the_action_deleting_its_branch():
    """create-pull-request never calls a close; with nothing to change it deletes the branch (only when delete-branch is
    on) and deleting the head branch of an open pull request closes it. It deletes only in its 'no diff' case."""
    pr = _only(OPEN_STEPS, "peter-evans/create-pull-request")
    assert re.search(r"(?m)^\s*delete-branch:\s*true\s*$", pr)


def test_the_pr_step_asks_github_the_right_questions_with_the_right_inputs():
    step = _step_with_id(PLAN_STEPS, "pr")
    env = dict(re.findall(r"(?m)^ {10}([A-Z_]+):\s*(\$\{\{.*?\}\})\s*$", step))
    assert env == {
        "GH_TOKEN": "${{ github.token }}",
        "REPO": "${{ github.repository }}",
        "OWNER": "${{ github.repository_owner }}",
        "BASE": "${{ github.ref_name }}",
        "CHANGED": "${{ steps.plan.outputs.changed }}",
    }
    body = _run_bodies(step)[0]
    assert "pulls?state=open&head=${OWNER}:base-update/website-base&per_page=100" in body
    assert "'[.[] | select(.base.ref == env.BASE)] | length'" in body, (
        "only pull requests into the running branch count"
    )
    assert "contents/infrastructure/docker/versions.env?ref=base-update/website-base" in body
    assert 'Accept: application/vnd.github.raw+json"' in body
    assert "|| { printf" in body and "exit 1; }" in body, "a failed compare must show its own error line"


def test_the_plan_jobs_outputs_come_from_the_steps_that_produce_them():
    block = re.search(r"(?m)^ {4}outputs:\n((?: {6}\S[^\n]*\n)+)", JOBS["plan"])
    assert block is not None
    outputs = dict(re.findall(r"(?m)^ {6}([a-z_]+):\s*(\$\{\{.*?\}\})\s*$", block.group(1)))
    assert outputs == {
        "changed": "${{ steps.plan.outputs.changed }}",
        "old": "${{ steps.plan.outputs.old }}",
        "new": "${{ steps.plan.outputs.new }}",
        "short": "${{ steps.plan.outputs.short }}",
        "python": "${{ steps.plan.outputs.python }}",
        "old_python": "${{ steps.plan.outputs.old_python }}",
        "website_sha": "${{ steps.website.outputs.sha }}",
        "compared": "${{ steps.registry.outputs.compared }}",
        "open_pr": "${{ steps.pr.outputs.open_pr }}",
    }


def test_github_token_is_read_only_and_every_job_has_a_timeout():
    assert re.search(r"(?m)^permissions:\s*\{\}\s*$", TEXT)
    allowed = {"plan": ["contents: read", "pull-requests: read"], "open-pr": ["contents: read"]}
    for name, body in JOBS.items():
        block = re.search(r"(?m)^ {4}permissions:\n((?: {6}\S[^\n]*\n)+)", body)
        assert block is not None, f"{name}: needs a permissions block"
        assert [line.strip() for line in block.group(1).splitlines()] == allowed[name], (
            f"{name}: GITHUB_TOKEN must be read-only"
        )
        assert re.search(r"(?m)^ {4}timeout-minutes:\s*\d+\s*$", body), f"{name}: needs a timeout"
    # The App token's inputs are `permission-*`, a different key; any other `<name>: write` would widen GITHUB_TOKEN.
    assert not re.search(r"(?m)^[ \t]+(?!permission-)[a-z-]+:[ \t]*write[ \t]*$", TEXT), (
        "a permissions: block grants write"
    )


def test_every_job_runs_on_the_program_runner_never_latest():
    runners = re.findall(r"(?m)^\s*runs-on:\s*(\S+)\s*$", CODE)
    assert runners == ["ubuntu-26.04", "ubuntu-26.04"]


def test_no_expression_is_pasted_into_a_shell_script_and_the_python_runs_isolated():
    bodies = _run_bodies(CODE)
    assert len(bodies) >= 6, "expected the run scripts of both jobs"
    for body in bodies:
        assert "${{" not in body, "an expression is interpolated into a run script"
    python_calls = re.findall(r"(?m)^.*\bpython3?\b.*$", "\n".join(bodies))
    assert len(python_calls) == 3 and all("python3 -I scripts/follow_website_base.py" in c for c in python_calls)
    assert sum("--check" in c for c in python_calls) == 1, "only one call is the read-only check"
    assert sum("--compare-env" in c for c in python_calls) == 1, "only one call compares the pull request branch"


def test_the_website_file_is_fetched_over_https_only_at_a_commit_with_limits():
    curls = re.findall(r"(?s)curl .*?-o ", CODE)
    assert len(curls) == 2
    for command in curls:
        for flag in ("--proto '=https'", "--proto-redir '=https'", "--tlsv1.2", "--max-time", "--max-filesize"):
            assert flag in command, f"curl lacks {flag}"
        assert "lab-image/versions.env" in command
    assert "/main/lab-image" not in CODE, "the file is read at a recorded commit, not at a moving branch"
    assert re.search(r"\^\[0-9a-f\]\{40\}\$", CODE), "the commit is checked to be a full SHA"


def test_every_checkout_drops_its_credentials_and_every_action_is_pinned_to_a_full_commit_sha():
    uses = re.findall(r"(?m)^\s*(?:- )?uses:\s*(\S+)", CODE)
    assert len(uses) == 4, "two checkouts, the App token and the pull request action"
    for reference in uses:
        assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", reference), f"{reference} is not pinned to a full SHA"
    checkouts = [s for s in PLAN_STEPS + OPEN_STEPS if "actions/checkout@" in s]
    assert len(checkouts) == 2
    for step in checkouts:
        assert re.search(r"(?m)^\s*with:\s*\{\s*persist-credentials:\s*false\s*\}\s*$", step), step


def test_every_action_pin_is_the_one_the_other_workflows_use():
    """Dependabot moves an action in every workflow file in one grouped pull request, so a pin that differs here would
    mean this file was edited by hand or missed."""
    others = "\n".join(p.read_text(encoding="utf-8") for p in WORKFLOWS.glob("*.yml") if p.name != "base-update.yml")
    for reference in re.findall(r"(?m)^\s*(?:- )?uses:\s*(\S+)", CODE):
        assert reference in others, f"{reference} is not used by any other workflow; check it against the others"


def test_the_two_older_checks_that_the_documents_name_still_exist():
    """CHANGELOG and the READMEs say the lint job and base-follows-website stay as the second line of defence."""
    ci = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    security = (WORKFLOWS / "security.yml").read_text(encoding="utf-8")
    assert "Base image digest in versions.env matches every FROM in the Dockerfile" in ci
    assert re.search(r"(?m)^  base-follows-website:\s*$", security)


# ---------------------------------------------------------------------------------------------------------------------
# Running the two decision scripts. They are the workflow's `run:` text, executed by bash with `docker` and `gh`
# replaced by small stand-ins that print canned answers, so the logic (platform comparison, "leave the open pull
# request alone") is tested for real without a registry, a network or a token.


def _find_bash() -> str | None:
    if sys.platform == "win32":
        for candidate in (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe"):
            if Path(candidate).is_file():
                return candidate
        return None
    return shutil.which("bash")


BASH = _find_bash()
needs_bash = pytest.mark.skipif(BASH is None, reason="bash is not available on this computer")


def _run_step(script: str, tmp_path: Path, env: dict[str, str], stubs: dict[str, str]):
    """Run one workflow `run:` script the way GitHub does (`bash -e file`), in the repository root. Returns the exit
    code, what it printed, and the lines it appended to $GITHUB_OUTPUT as a dict."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in stubs.items():
        (bin_dir / name).write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8", newline="\n")
        (bin_dir / name).chmod(0o755)
    (bin_dir / "python3").write_text(
        f'#!/usr/bin/env bash\nexec "{Path(sys.executable).as_posix()}" "$@"\n', encoding="utf-8", newline="\n"
    )
    (bin_dir / "python3").chmod(0o755)
    runner_temp = tmp_path / "runner"
    runner_temp.mkdir()
    output = tmp_path / "github_output"
    output.write_text("", encoding="utf-8")
    script_file = tmp_path / "step.sh"
    script_file.write_text(script, encoding="utf-8", newline="\n")
    full_env = {
        **os.environ,
        **env,
        "PATH": os.pathsep.join([bin_dir.as_posix(), os.environ.get("PATH", "")]),
        "GITHUB_OUTPUT": output.as_posix(),
        "RUNNER_TEMP": runner_temp.as_posix(),
    }
    assert BASH is not None
    result = subprocess.run(
        [BASH, "-e", script_file.as_posix()], cwd=ROOT, env=full_env, capture_output=True, text=True, timeout=180
    )
    outputs = dict(line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines() if "=" in line)
    return result.returncode, result.stdout + result.stderr, outputs


def _index(platforms: list[str]) -> str:
    """What `docker buildx imagetools inspect` prints for an index: a header, then one block per manifest. Real indexes
    also list attestation manifests as unknown/unknown, which the step must ignore."""
    blocks = "".join(
        f"  Name:        docker.io/library/python@sha256:{i:064x}\n"
        f"  MediaType:   application/vnd.oci.image.manifest.v1+json\n"
        f"  Platform:    {platform}\n\n"
        for i, platform in enumerate([*platforms, "unknown/unknown"], start=1)
    )
    return (
        f"Name:      docker.io/library/python:3.14.8-slim-trixie@sha256:{0:064x}\n"
        "MediaType: application/vnd.oci.image.index.v1+json\n"
        f"Digest:    sha256:{0:064x}\n\nManifests:\n{blocks}"
    )


OLD_REF = "python:3.14.8-slim-trixie@sha256:" + "a" * 64
NEW_REF = "python:3.14.8-slim-trixie@sha256:" + "b" * 64
REGISTRY_SCRIPT = _run_bodies(_step_with_id(PLAN_STEPS, "registry"))[0]
DOCKER_STUB = """\
# usage: docker buildx imagetools inspect <ref>
[ "$1 $2 $3" = "buildx imagetools inspect" ] || exit 2
case "$4" in
  "$NEW_REF") [ -f "$STUB_DIR/new.txt" ] && cat "$STUB_DIR/new.txt" || { echo "not found" >&2; exit 1; } ;;
  "$OLD_REF") [ -f "$STUB_DIR/old.txt" ] && cat "$STUB_DIR/old.txt" || { echo "not found" >&2; exit 1; } ;;
  *) echo "unexpected ref" >&2; exit 2 ;;
esac
"""


def _registry(tmp_path: Path, new: str | None, old: str | None):
    stub_dir = tmp_path / "answers"
    stub_dir.mkdir()
    if new is not None:
        (stub_dir / "new.txt").write_text(new, encoding="utf-8", newline="\n")
    if old is not None:
        (stub_dir / "old.txt").write_text(old, encoding="utf-8", newline="\n")
    env = {"OLD_REF": OLD_REF, "NEW_REF": NEW_REF, "STUB_DIR": stub_dir.as_posix()}
    return _run_step(REGISTRY_SCRIPT, tmp_path, env, {"docker": DOCKER_STUB})


@needs_bash
def test_registry_step_passes_when_the_new_index_has_every_platform_the_old_one_had(tmp_path):
    both = _index(["linux/amd64", "linux/arm64/v8"])
    code, log, outputs = _registry(tmp_path, new=both, old=both)
    assert code == 0, log
    assert outputs == {"compared": "true"}


@needs_bash
def test_registry_step_passes_when_the_new_index_adds_a_platform(tmp_path):
    code, log, outputs = _registry(tmp_path, new=_index(["linux/amd64", "linux/arm64/v8"]), old=_index(["linux/amd64"]))
    assert code == 0, log
    assert outputs == {"compared": "true"}


@needs_bash
def test_registry_step_fails_when_the_new_index_lacks_a_platform_the_old_one_had(tmp_path):
    code, log, outputs = _registry(tmp_path, new=_index(["linux/amd64"]), old=_index(["linux/amd64", "linux/arm64/v8"]))
    assert code == 1
    assert "linux/arm64/v8" in log and "::error::" in log
    assert "compared" not in outputs


@needs_bash
def test_registry_step_fails_when_the_new_digest_has_no_linux_amd64(tmp_path):
    code, log, _ = _registry(tmp_path, new=_index(["linux/arm64/v8"]), old=_index(["linux/arm64/v8"]))
    assert code == 1 and "linux/amd64" in log


@needs_bash
def test_registry_step_fails_when_the_new_digest_is_not_an_index(tmp_path):
    single = (
        f"Name:      docker.io/library/python@sha256:{1:064x}\nMediaType: application/vnd.oci.image.manifest.v1+json\n"
    )
    code, log, _ = _registry(tmp_path, new=single, old=_index(["linux/amd64"]))
    assert code == 1 and "not an index" in log


@needs_bash
def test_registry_step_fails_when_the_registry_does_not_show_the_new_digest(tmp_path):
    code, log, _ = _registry(tmp_path, new=None, old=_index(["linux/amd64"]))
    assert code == 1 and "did not show" in log


@needs_bash
def test_registry_step_only_warns_when_the_old_digest_can_no_longer_be_shown_and_says_it_did_not_compare(tmp_path):
    code, log, outputs = _registry(tmp_path, new=_index(["linux/amd64", "linux/arm64/v8"]), old=None)
    assert code == 0, log
    assert "::warning::" in log
    assert outputs == {"compared": "false"}, "the pull request box must stay unticked"


WEBSITE_ENV = "BASE_IMAGE=python:3.14.9-slim-trixie\nBASE_DIGEST=sha256:" + "b" * 64 + "\nBASE_PYTHON_VERSION=3.14.9\n"
OLDER_ENV = "BASE_IMAGE=python:3.14.8-slim-trixie\nBASE_DIGEST=sha256:" + "a" * 64 + "\nBASE_PYTHON_VERSION=3.14.8\n"
PR_SCRIPT = _run_bodies(_step_with_id(PLAN_STEPS, "pr"))[0]
GH_STUB = """\
# usage: gh api <url> [--jq ...] [-H ...]; prints what the real API would for the cases the step asks about
[ "$1" = "api" ] || exit 2
case "$2" in
  *"/pulls?"*) printf '%s\\n' "$STUB_PR_COUNT" ;;
  *"/contents/infrastructure/docker/versions.env?ref=base-update/website-base"*)
    [ -f "$STUB_DIR/branch.env" ] || { echo "gh: No commit found (HTTP 404)" >&2; exit 1; }
    cat "$STUB_DIR/branch.env" ;;
  *) echo "unexpected url" >&2; exit 2 ;;
esac
"""


def _decide(tmp_path: Path, changed: bool, pull_requests: str, branch_env: str | None):
    stub_dir = tmp_path / "answers"
    stub_dir.mkdir()
    if branch_env is not None:
        (stub_dir / "branch.env").write_text(branch_env, encoding="utf-8", newline="\n")
    env = {
        "GH_TOKEN": "unused",
        "REPO": "example/repo",
        "OWNER": "example",
        "BASE": "main",
        "CHANGED": "true" if changed else "false",
        "STUB_PR_COUNT": pull_requests,
        "STUB_DIR": stub_dir.as_posix(),
    }
    # The earlier step of the real job downloads the website's file into $RUNNER_TEMP; here it is written first.
    wrapped = f"printf '%s' '{WEBSITE_ENV}' > \"$RUNNER_TEMP/website-versions.env\"\n" + PR_SCRIPT
    return _run_step(wrapped, tmp_path, env, {"gh": GH_STUB})


@needs_bash
def test_a_move_with_no_open_pull_request_gives_the_second_job_work(tmp_path):
    code, log, outputs = _decide(tmp_path, changed=True, pull_requests="0", branch_env=None)
    assert code == 0, log
    assert outputs["open_pr"] == "true"


@needs_bash
def test_an_open_pull_request_that_already_holds_the_websites_pin_is_left_alone(tmp_path):
    """The case that protects a fix a person pushed to the branch: the daily run must not rebuild the branch."""
    code, log, outputs = _decide(tmp_path, changed=True, pull_requests="1", branch_env=WEBSITE_ENV)
    assert code == 0, log
    assert outputs["open_pr"] == "false"
    assert "left alone" in log


@needs_bash
def test_an_open_pull_request_with_an_older_pin_is_rebuilt_when_the_website_moved_again(tmp_path):
    code, log, outputs = _decide(tmp_path, changed=True, pull_requests="1", branch_env=OLDER_ENV)
    assert code == 0, log
    assert outputs["open_pr"] == "true"


@needs_bash
def test_an_open_pull_request_whose_branch_file_is_malformed_is_rebuilt(tmp_path):
    code, log, outputs = _decide(tmp_path, changed=True, pull_requests="1", branch_env="BASE_IMAGE=oops\n")
    assert code == 0, log
    assert outputs["open_pr"] == "true"


@needs_bash
def test_nothing_to_move_and_no_open_pull_request_ends_the_run_in_the_plan(tmp_path):
    code, log, outputs = _decide(tmp_path, changed=False, pull_requests="0", branch_env=None)
    assert code == 0, log
    assert outputs["open_pr"] == "false"


@needs_bash
def test_nothing_to_move_but_an_open_pull_request_lets_the_action_close_it(tmp_path):
    code, log, outputs = _decide(tmp_path, changed=False, pull_requests="1", branch_env=None)
    assert code == 0, log
    assert outputs["open_pr"] == "true"
    assert "obsolete" in log


@needs_bash
def test_when_the_branch_file_cannot_be_read_the_step_fails_instead_of_rebuilding_the_branch(tmp_path):
    code, log, outputs = _decide(tmp_path, changed=True, pull_requests="1", branch_env=None)
    assert code != 0, "a failed read must not be taken as 'the branch is not current'"
    assert "open_pr" not in outputs


@needs_bash
def test_a_pull_request_count_that_is_not_a_number_fails_the_step(tmp_path):
    code, log, outputs = _decide(tmp_path, changed=True, pull_requests="oops", branch_env=None)
    assert code != 0 and "open_pr" not in outputs
