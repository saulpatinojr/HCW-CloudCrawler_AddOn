"""core-update.yml keeps the HCW Main Admin App key away from upstream code, and opens its bump pull request with the
App token, never with GITHUB_TOKEN.

Two jobs. `bump` runs the new engine (through this edition's lint and tests) with a read-only GITHUB_TOKEN and no
secret. `pull-request` runs no project or engine code: it works out the tags again, regenerates the bump with this
checkout's scripts/bump_core_pin.py and `uv lock --no-build`, refuses an artifact that differs, and only then mints the
App token and opens the pull request. Code that runs in a step can reach the later steps of the same job, which is why
the key must never be in a job that ran upstream code. A pull request opened with GITHUB_TOKEN starts no workflow, so
the required checks never run on it and it can never merge. The App's client ID is the repository variable
HCW_MAIN_ADMIN_CLIENT_ID and its private key is the repository secret HCW_MAIN_ADMIN_PRIVATE_KEY; no job runs in an
environment. These are static checks of the workflow text; they do not prove the credential works. A run with
probe=true does (see the header of the workflow). tests/unit/test_bump_core_pin.py runs the pull-request job's apply
step itself against good and tampered artifacts."""

import re

from ..conftest import ROOT

TEXT = (ROOT / ".github" / "workflows" / "core-update.yml").read_text(encoding="utf-8")
_PARTS = re.split(r"(?m)^  ([a-z-]+):\n", TEXT.split("\njobs:\n", 1)[1])[1:]
JOBS = dict(zip(_PARTS[::2], _PARTS[1::2], strict=True))  # job id -> its text
BUMP = re.split(r"(?m)^ {6}- ", JOBS["bump"].split("\n    steps:\n", 1)[1])[1:]
PR = re.split(r"(?m)^ {6}- ", JOBS["pull-request"].split("\n    steps:\n", 1)[1])[1:]
STEPS = BUMP + PR
APP_STEP_OUTPUT = r"\$\{\{\s*steps\.app-token\.outputs\.token\s*\}\}"
# What "project code" looks like in a step: anything that installs or runs this repository's or the engine's code.
PROJECT_CODE = re.compile(r"\buv\s|uv==|\bpip\s|pytest|\bnpm\b|\bnpx\b|\bmake\b|ruff|scripts/|python -m|setup-python")


def _field(step: str, key: str) -> str:
    """The value of a step's own key (`if`, `id`, `uses`, `name`), or an empty string."""
    found = re.search(rf"(?m)^(?: {{8}})?{re.escape(key)}:[ \t]*(.*)$", step)
    return found.group(1).strip() if found else ""


def _with(step: str, key: str) -> str:
    """The value of a key under the step's `with:` (indented ten spaces), or of the inline `with: { ... }` form."""
    found = re.search(rf"(?m)^ {{10}}{re.escape(key)}:[ \t]*(.*)$", step)
    if found:
        return found.group(1).strip()
    inline = re.search(rf"(?m)^ {{8}}with:\s*\{{[^}}]*\b{re.escape(key)}:\s*([^,}}]+)", step)
    return inline.group(1).strip() if inline else ""


def _uses(steps: list[str], action: str) -> list[str]:
    return [s for s in steps if _field(s, "uses").split("@")[0] == action]


def _only(steps: list[str], action: str) -> str:
    found = _uses(steps, action)
    assert len(found) == 1, f"expected exactly one step using {action}"
    return found[0]


def _by_id(steps: list[str], step_id: str) -> str:
    found = [s for s in steps if _field(s, "id") == step_id]
    assert len(found) == 1, f"expected exactly one step with id {step_id}"
    return found[0]


def _commands(steps: list[str]) -> str:
    """Every shell script of the given steps (the `run:` values), without comments and quoted messages."""
    lines = []
    for step in steps:
        block = re.search(r"(?ms)^ {8}run: (?:\|\n(.*)|(.*?)$)", step)
        if block:
            body = block.group(1) if block.group(1) is not None else block.group(2)
            lines += [ln for ln in body.splitlines() if not ln.strip().startswith("#")]
    return re.sub(r"'[^'\n]*'|\"[^\"\n]*\"", '""', "\n".join(lines))


def test_two_jobs_the_pull_request_job_needs_the_bump_job():
    assert list(JOBS) == ["bump", "pull-request"], "expected the jobs bump and pull-request, in that order"
    assert re.search(r"(?m)^    needs: bump$", JOBS["pull-request"])
    assert re.search(r"(?m)^      changed: \$\{\{ steps\.refs\.outputs\.changed \}\}$", JOBS["bump"])


def test_pull_request_is_opened_with_the_app_token_never_github_token():
    app = _only(PR, "actions/create-github-app-token")
    pr = _only(PR, "peter-evans/create-pull-request")
    assert _field(app, "id") == "app-token"
    assert PR.index(app) < PR.index(pr), "the App token step must come before the pull request step"
    assert re.fullmatch(APP_STEP_OUTPUT, _with(pr, "token"))
    assert "GITHUB_TOKEN" not in pr, "create-pull-request must not be given GITHUB_TOKEN"


def test_every_step_that_runs_gh_pr_uses_the_app_token_after_it_was_minted():
    app = _only(PR, "actions/create-github-app-token")
    gh_pr = [s for s in STEPS if re.search(r"\bgh pr\b", s)]
    assert gh_pr, "the auto-merge step is missing"
    for step in gh_pr:
        assert step in PR
        assert re.search(rf"GH_TOKEN:\s*{APP_STEP_OUTPUT}", step)
        assert PR.index(app) < PR.index(step)


def test_token_is_minted_only_after_the_artifact_was_checked_and_applied():
    # The compatibility check runs in the bump job, which the pull-request job needs, so it has finished before any
    # step of this job; inside this job, the token comes after the apply step and only when it succeeded.
    assert len([s for s in STEPS if _field(s, "id") == "compat"]) == 1
    assert _by_id(BUMP, "compat")
    apply = _by_id(PR, "apply")
    app = _only(PR, "actions/create-github-app-token")
    assert PR.index(_by_id(PR, "expect")) < PR.index(apply) < PR.index(app)
    assert _field(app, "if") == "inputs.probe || steps.apply.outcome == 'success'"


def test_token_action_is_pinned_to_a_full_commit_sha():
    app = _only(PR, "actions/create-github-app-token")
    assert re.fullmatch(r"actions/create-github-app-token@[0-9a-f]{40}( # .*)?", _field(app, "uses"))


def test_app_credential_is_the_hcw_main_admin_variable_and_secret():
    app = _only(PR, "actions/create-github-app-token")
    assert _with(app, "client-id") == "${{ vars.HCW_MAIN_ADMIN_CLIENT_ID }}"
    assert _with(app, "private-key") == "${{ secrets.HCW_MAIN_ADMIN_PRIVATE_KEY }}"
    # Only the token step is given the key.
    with_key = [s for s in STEPS if "secrets.HCW_MAIN_ADMIN_PRIVATE_KEY" in s]
    assert with_key == [app], "the private key must reach the token step and no other step"
    assert TEXT.count("secrets.HCW_MAIN_ADMIN_PRIVATE_KEY") == 1


def test_workflow_reads_no_other_secrets():
    names = set(re.findall(r"secrets\.([A-Za-z0-9_]+)", TEXT))
    assert names == {"GITHUB_TOKEN", "HCW_MAIN_ADMIN_PRIVATE_KEY"}
    for leak in ("toJSON(secrets", "secrets[", "secrets: inherit"):
        assert leak not in TEXT, f"{leak} would hand more than the one key to a step"


def test_app_token_is_limited_to_this_repository():
    app = _only(PR, "actions/create-github-app-token")
    # With `owner` set and `repositories` empty the action mints a token for every repository of the installation.
    # With no `owner`, an empty `repositories` falls back to the current repository, so this shape fails closed.
    assert not re.search(r"(?m)^\s*owner:", app), "owner must not be set: an empty repositories would widen the token"
    # One value, this repository's full name: not a list, not a wildcard, not another repository.
    assert _with(app, "repositories") == "${{ github.repository }}"


def test_app_token_permissions_are_exactly_contents_and_pull_requests_write():
    app = _only(PR, "actions/create-github-app-token")
    granted = dict(re.findall(r"(?m)^\s*permission-([a-z-]+):\s*([a-z]+)\b", app))
    assert granted == {"contents": "write", "pull-requests": "write"}


def test_old_app_credential_is_gone():
    for old in ("admin-ops", "APP_CLIENT_ID", "APP_PRIVATE_KEY"):
        assert old not in TEXT, f"{old} must not appear in core-update.yml"
    assert "portfolio" not in TEXT.lower(), "the Portfolio App must not appear in core-update.yml"


def test_no_job_runs_in_an_environment():
    # The credential is a repository variable and secret, so no environment is needed (or wanted) on a job.
    assert not re.search(r"(?m)^\s*environment:", TEXT)


def test_empty_top_level_permissions_and_read_only_github_token_in_both_jobs():
    assert re.search(r"(?m)^permissions: \{\}\s*$", TEXT), "top-level permissions must stay empty"
    assert len(re.findall(r"(?m)^\s*permissions:\s*\{", TEXT)) == 1, "only the top level may use the inline form"
    for name, job in JOBS.items():
        assert re.search(r"(?m)^    permissions:\n      contents: read\n    [a-z]", job), f"{name}: contents: read only"
    assert len(re.findall(r"(?m)^\s*permissions:", TEXT)) == 3
    # The App token's inputs are `permission-*`, a different key; any other `<name>: write` would widen GITHUB_TOKEN.
    write_grant = re.search(r"(?m)^[ \t]+(?!permission-)[a-z-]+:[ \t]*write[ \t]*$", TEXT)
    assert not write_grant, "a permissions: block grants write"


def test_every_action_is_pinned_to_a_full_commit_sha():
    uses = [u for u in re.findall(r"(?m)^[ \t]*(?:- )?uses:[ \t]*(\S+)", TEXT) if not u.startswith("./")]
    assert len(uses) >= 8
    for use in uses:
        assert re.search(r"@[0-9a-f]{40}$", use), f"{use} is not pinned to a commit SHA"


def test_both_checkouts_persist_no_credentials():
    for steps in (BUMP, PR):
        checkout = _only(steps, "actions/checkout")
        assert _with(checkout, "persist-credentials") == "false"


def test_the_bump_job_holds_no_secret_and_no_app_credential():
    bump = JOBS["bump"]
    assert "HCW_MAIN_ADMIN" not in bump and "create-github-app-token" not in bump
    assert not _uses(BUMP, "peter-evans/create-pull-request")
    assert not re.search(r"\bgh pr\b", bump)
    assert set(re.findall(r"secrets\.([A-Za-z0-9_]+)", bump)) <= {"GITHUB_TOKEN"}


def test_no_step_that_runs_project_code_in_the_bump_job_is_given_a_token():
    runs_code = [s for s in BUMP if PROJECT_CODE.search(s)]
    assert len(runs_code) >= 4, "expected the setup, install, bump and compatibility steps"
    for step in runs_code:
        assert "GH_TOKEN" not in step and "secrets." not in step, _field(step, "name")
    # GITHUB_TOKEN reaches the refs step only (the upstream releases API), which runs no project code and comes first.
    with_token = [s for s in BUMP if "GH_TOKEN" in s or "secrets." in s]
    assert [_field(s, "id") for s in with_token] == ["refs"]
    assert all(BUMP.index(s) < min(BUMP.index(c) for c in runs_code) for s in with_token)
    assert not PROJECT_CODE.search(_commands(with_token))


def test_the_pull_request_job_runs_no_project_or_engine_code():
    scripts = _commands(PR)
    assert "gh pr merge" in scripts and "cmp -s" in scripts, "the run blocks were not found"
    # uv only to lock, never to build, sync, run, export or install; and every lock is --no-build.
    assert re.findall(r"\buv\s+(\S+)", scripts) == ["lock"]
    for line in scripts.splitlines():
        if re.search(r"\buv\s+lock\b", line):
            assert "--no-build" in line, line
    assert not re.search(r"\buvx\b", scripts)
    # python only for this checkout's bump script, in isolated mode, and for the hash-checked uv install.
    calls = re.findall(r"\bpython3?\s+(.*)", scripts)
    assert calls, "expected python calls"
    for call in calls:
        assert call.startswith(("-I scripts/bump_core_pin.py ", "-m pip install --require-hashes --no-deps -r ")), call
    assert set(re.findall(r"scripts/\S+", scripts)) == {"scripts/bump_core_pin.py"}
    for word in (r"\bpytest\b", r"\bnpx\s", r"\bnpm\s", r"\bmake\s", r"\bruff\b", r"\bpip\s+install\s+(?!--require)"):
        assert not re.search(word, scripts), f"the pull-request job must not run project or engine code ({word})"


def test_the_pull_request_job_installs_the_same_uv_as_the_bump_job_by_hash():
    version = re.findall(r'"uv==([0-9.]+)"', JOBS["bump"])
    hashed = re.findall(r"uv==([0-9.]+) --hash=sha256:[0-9a-f]{64}\b", JOBS["pull-request"])
    assert len(version) == 1 and hashed == version, "move the uv hash in the pull-request job with the uv version"
    assert not re.search(r"uv==[0-9.]+\"", JOBS["pull-request"]), "the pull-request job installs uv by hash only"


def test_the_bump_job_hands_over_one_artifact_and_the_other_job_downloads_it_before_the_check():
    up = _only(BUMP, "actions/upload-artifact")
    down = _only(PR, "actions/download-artifact")
    assert _with(up, "name") == _with(down, "name") == "core-bump"
    assert PR.index(down) < PR.index(_by_id(PR, "apply"))


def test_the_apply_step_regenerates_both_files_and_refuses_any_difference():
    apply = _by_id(PR, "apply")
    assert "GH_TOKEN" not in apply and "secrets." not in apply and "needs.bump.outputs" not in apply
    assert re.search(r"(?m)^\s+env: \{ LATEST: \"\$\{\{ steps\.expect\.outputs\.latest \}\}\",", apply)
    assert 'CURRENT: "${{ steps.expect.outputs.current }}"' in apply
    # A refusal resets the checkout before it stops, so nothing half-applied can reach a later step.
    assert re.search(r"refuse\(\) \{[^}]*git reset -q --hard HEAD;[^}]*exit 1; \}", apply)
    for check in (
        'python -I scripts/bump_core_pin.py bump --from "$CURRENT" --tag "$LATEST"',
        "uv lock --no-build --upgrade-package cloud-crawler-core",
        "python -I scripts/bump_core_pin.py check-lock",
        'cmp -s pyproject.toml "$dir/pyproject.toml"',
        'cmp -s uv.lock "$dir/uv.lock"',
        '"outcome,pyproject.toml,uv.lock"',
        "printf 'success\\n'",
        "printf 'failure\\n'",
        "git status --porcelain",
    ):
        assert check in apply, check
    # No file is taken from the artifact: it is only compared.
    assert not re.search(r"\bcp\b|\bmv\b|\btar\b|\bunzip\b", _commands([apply]))


def test_the_tags_are_worked_out_again_in_the_pull_request_job():
    expect = _by_id(PR, "expect")
    assert "needs.bump.outputs" not in expect
    assert 'gh api "repos/${UPSTREAM}/releases/latest"' in expect
    assert not PROJECT_CODE.search(expect)
    # The token-holding steps of this job come before any code runs, and run none themselves.
    with_github_token = [s for s in PR if "secrets.GITHUB_TOKEN" in s]
    assert with_github_token == [expect]
    assert "needs.bump.outputs" not in "".join(PR[PR.index(expect) :]), "later steps must not read the bump job's tags"


def test_auto_merge_never_reads_the_untrusted_outcome():
    merge = [s for s in STEPS if re.search(r"\bgh pr merge\b", s)]
    assert len(merge) == 1
    condition = _field(merge[0], "if")
    # The outcome comes from the job that ran upstream code, so it must not decide the merge. What does: the repository
    # variable, this job's own byte-for-byte check, and GitHub's required checks on the pull request.
    for part in (
        "steps.apply.outcome == 'success'",
        "vars.CORE_AUTOMERGE == 'true'",
        "steps.pr.outputs.pull-request-number != ''",
        "!inputs.probe",
    ):
        assert part in condition, part
    assert not re.search(r"outputs\.outcome|bump/outcome", merge[0]), "the auto-merge step must not read the outcome"
    assert 'gh pr merge --squash --auto "$PR_NUMBER"' in merge[0], "auto-merge waits for the required checks"
    assert "--admin" not in merge[0]
    # The outcome reaches only the pull request's text (title, labels, body) and a warning that holds no token.
    readers = [s for s in PR if "steps.apply.outputs.outcome" in s]
    pr = _only(PR, "peter-evans/create-pull-request")
    assert len(readers) == 2 and pr in readers
    warning = next(s for s in readers if s is not pr)
    assert not re.search(r"GH_TOKEN|secrets\.|app-token|\bgh\b", warning), "the warning step must hold no token"


REFUSE_NAME = "name: Refuse a run that is not on main"


def test_both_jobs_refuse_a_run_that_is_not_on_main_first_and_visibly():
    for name, steps in (("bump", BUMP), ("pull-request", PR)):
        first = steps[0]
        assert first.startswith(REFUSE_NAME), f"{name}: the first step must be the main-only refusal"
        assert not _field(first, "if"), f"{name}: the refusal must always run"
        assert re.search(r'(?m)^ {8}env: \{ RUN_REF: "\$\{\{ github\.ref \}\}" \}$', first), name
        block = first.split("run: |\n", 1)[1]
        assert 'if [ "$RUN_REF" != "refs/heads/main" ]; then' in block
        assert re.search(r'echo "::error::[^"]*\$\{RUN_REF\}[^"]*"', block), f"{name}: the error must name the ref"
        assert re.search(r"(?m)^\s*exit 1$", block)
        assert "${{" not in block, f"{name}: no expression inside the shell"
    # A job-level `if:` would skip the bump job in silence; the pull-request job is also gated by one.
    assert not re.search(r"(?m)^    if:", JOBS["bump"]), "the bump job must refuse, not be skipped silently"
    job_if = "if: github.ref == 'refs/heads/main' && (needs.bump.outputs.changed == 'true' || inputs.probe)"
    assert re.search(rf"(?m)^    {re.escape(job_if)}$", JOBS["pull-request"])


def test_both_checkouts_take_the_commit_the_run_was_started_for_after_the_refusal():
    for name, steps in (("bump", BUMP), ("pull-request", PR)):
        checkout = _only(steps, "actions/checkout")
        with_line = 'with: { persist-credentials: false, ref: "${{ github.sha }}" }'
        assert re.search(rf"(?m)^ {{8}}{re.escape(with_line)}$", checkout), name
        assert steps.index(checkout) > 0 and steps[0].startswith(REFUSE_NAME), name
    # A checkout of a commit is a detached HEAD, where create-pull-request needs the base named.
    assert _with(_only(PR, "peter-evans/create-pull-request"), "base") == "main"


def test_bump_pull_request_adds_only_the_two_bump_files():
    pr = _only(PR, "peter-evans/create-pull-request")
    paths = pr.split("add-paths: |\n", 1)[1].split("\n          body:", 1)[0].split()
    assert paths == ["pyproject.toml", "uv.lock"]
    for path in paths:
        assert (ROOT / path).is_file(), path


def test_a_probe_run_never_reaches_a_step_that_writes_or_runs_code():
    # A manual run with probe=true must stay read-only even when a newer release exists (changed == 'true').
    writers = _uses(PR, "peter-evans/create-pull-request") + [s for s in PR if re.search(r"\bgh pr\b", s)]
    assert len(writers) == 2, "expected the pull request step and the auto-merge step"
    for step in writers:
        assert "!inputs.probe" in _field(step, "if"), "a step that writes must be skipped on a probe"
    for step in STEPS:
        if PROJECT_CODE.search(step) or _uses([step], "actions/upload-artifact"):
            assert "!inputs.probe" in _field(step, "if"), _field(step, "name") or _field(step, "uses")


def test_probe_step_only_reads_and_checks_the_token_covers_this_repository_only():
    probe = [s for s in STEPS if _field(s, "if") == "inputs.probe"]
    assert len(probe) == 1, "expected exactly one probe step"
    run = probe[0]
    assert run in PR
    assert re.search(r'gh api "repos/\$\{REPO\}"', run)
    assert re.search(r"gh api installation/repositories", run)
    assert re.search(r'test "\$\{covered\}" = "\$\{REPO\}"', run), "the probe must fail if the token covers more"
    # `gh api` turns into a POST as soon as it is given a field, so fields and bodies are as forbidden as -X, with
    # the value attached (-XPOST, -fname=value) or separate.
    writes = r"\bgh pr\b|\bgit\b|--method|\s-[XfF]|--field|--raw-field|--input"
    assert not re.search(writes, run), "the probe must not write"
