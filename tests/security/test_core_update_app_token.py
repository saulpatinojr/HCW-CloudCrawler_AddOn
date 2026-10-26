"""core-update.yml opens its bump pull request with the HCW Main Admin GitHub App token, never with GITHUB_TOKEN.

A pull request opened with GITHUB_TOKEN starts no workflow, so the required checks never run on it and it can never
merge. The App's client ID is the repository variable HCW_MAIN_ADMIN_CLIENT_ID and its private key is the repository
secret HCW_MAIN_ADMIN_PRIVATE_KEY; the job does not run in an environment. These are static checks of the workflow
text; they do not prove the credential works. A run with probe=true does (see the header of the workflow)."""

import re

from ..conftest import ROOT

TEXT = (ROOT / ".github" / "workflows" / "core-update.yml").read_text(encoding="utf-8")
JOBS = TEXT.split("\njobs:\n", 1)[1]
STEPS = re.split(r"(?m)^ {6}- ", JOBS)[1:]  # the steps of the one job
APP_STEP_OUTPUT = r"\$\{\{\s*steps\.app-token\.outputs\.token\s*\}\}"


def _only(action: str) -> str:
    found = [s for s in STEPS if re.search(rf"(?m)^\s*uses:\s*{re.escape(action)}@", s)]
    assert len(found) == 1, f"expected exactly one step using {action}"
    return found[0]


def test_pull_request_is_opened_with_the_app_token_never_github_token():
    app = _only("actions/create-github-app-token")
    pr = _only("peter-evans/create-pull-request")
    assert re.search(r"(?m)^\s*id:\s*app-token\s*$", app)
    assert STEPS.index(app) < STEPS.index(pr), "the App token step must come before the pull request step"
    assert re.search(rf"(?m)^\s*token:\s*{APP_STEP_OUTPUT}\s*$", pr)
    assert "GITHUB_TOKEN" not in pr, "create-pull-request must not be given GITHUB_TOKEN"


def test_every_step_that_runs_gh_pr_uses_the_app_token_after_it_was_minted():
    app = _only("actions/create-github-app-token")
    gh_pr = [s for s in STEPS if re.search(r"\bgh pr\b", s)]
    assert gh_pr, "the auto-merge step is missing"
    for step in gh_pr:
        assert re.search(rf"GH_TOKEN:\s*{APP_STEP_OUTPUT}", step)
        assert STEPS.index(app) < STEPS.index(step)


def test_token_is_minted_late_after_the_compatibility_check():
    app = _only("actions/create-github-app-token")
    compat = [s for s in STEPS if re.search(r"(?m)^\s*id:\s*compat\s*$", s)]
    assert len(compat) == 1, "expected exactly one compatibility step"
    assert STEPS.index(compat[0]) < STEPS.index(app), "the App token must be minted after the tests have run"


def test_token_action_is_pinned_to_a_full_commit_sha():
    app = _only("actions/create-github-app-token")
    assert re.search(r"(?m)^\s*uses:\s*actions/create-github-app-token@[0-9a-f]{40}(\s|$)", app)


def test_app_credential_is_the_hcw_main_admin_variable_and_secret():
    app = _only("actions/create-github-app-token")
    assert re.search(r"(?m)^\s*client-id:\s*\$\{\{\s*vars\.HCW_MAIN_ADMIN_CLIENT_ID\s*\}\}\s*$", app)
    assert re.search(r"(?m)^\s*private-key:\s*\$\{\{\s*secrets\.HCW_MAIN_ADMIN_PRIVATE_KEY\s*\}\}\s*$", app)
    # Only the token step is given the key.
    with_key = [s for s in STEPS if "secrets.HCW_MAIN_ADMIN_PRIVATE_KEY" in s]
    assert with_key == [app], "the private key must reach the token step and no other step"


def test_workflow_reads_no_other_secrets():
    names = set(re.findall(r"secrets\.([A-Za-z0-9_]+)", TEXT))
    assert names == {"GITHUB_TOKEN", "HCW_MAIN_ADMIN_PRIVATE_KEY"}
    for leak in ("toJSON(secrets", "secrets[", "secrets: inherit"):
        assert leak not in TEXT, f"{leak} would hand more than the one key to a step"


def test_app_token_is_limited_to_this_repository():
    app = _only("actions/create-github-app-token")
    # With `owner` set and `repositories` empty the action mints a token for every repository of the installation.
    # With no `owner`, an empty `repositories` falls back to the current repository, so this shape fails closed.
    assert not re.search(r"(?m)^\s*owner:", app), "owner must not be set: an empty repositories would widen the token"
    # One value, this repository's full name: not a list, not a wildcard, not another repository.
    assert re.search(r"(?m)^\s*repositories:\s*\$\{\{\s*github\.repository\s*\}\}\s*$", app)


def test_app_token_permissions_are_exactly_contents_and_pull_requests_write():
    app = _only("actions/create-github-app-token")
    granted = dict(re.findall(r"(?m)^\s*permission-([a-z-]+):\s*([a-z]+)\b", app))
    assert granted == {"contents": "write", "pull-requests": "write"}


def test_old_app_credential_is_gone():
    for old in ("admin-ops", "APP_CLIENT_ID", "APP_PRIVATE_KEY"):
        assert old not in TEXT, f"{old} must not appear in core-update.yml"
    assert "portfolio" not in TEXT.lower(), "the Portfolio App must not appear in core-update.yml"


def test_job_does_not_run_in_an_environment():
    # The credential is a repository variable and secret, so no environment is needed (or wanted) on the job.
    assert not re.search(r"(?m)^\s*environment:", TEXT)


def test_one_job_and_an_empty_top_level_permissions_block():
    assert re.search(r"(?m)^permissions: \{\}\s*$", TEXT), "top-level permissions must stay empty"
    assert len(re.findall(r"(?m)^ {2}[A-Za-z0-9_-]+:\s*$", JOBS)) == 1, "expected exactly one job"
    assert len(re.findall(r"(?m)^\s*permissions:\s*\{", TEXT)) == 1, "only the top level may use the inline form"


def test_github_token_is_read_only():
    assert re.search(r"(?m)^ {4}permissions:\n {6}contents:\s*read\s*$", TEXT)
    # The App token's inputs are `permission-*`, a different key; any other `<name>: write` would widen GITHUB_TOKEN.
    write_grant = re.search(r"(?m)^[ \t]+(?!permission-)[a-z-]+:[ \t]*write[ \t]*$", TEXT)
    assert not write_grant, "a permissions: block grants write"


def test_every_action_is_pinned_to_a_full_commit_sha():
    uses = [u for u in re.findall(r"(?m)^[ \t]*(?:- )?uses:[ \t]*(\S+)", TEXT) if not u.startswith("./")]
    assert len(uses) >= 4
    for use in uses:
        assert re.search(r"@[0-9a-f]{40}$", use), f"{use} is not pinned to a commit SHA"


def test_a_probe_run_never_reaches_a_step_that_writes():
    # A manual run with probe=true must stay read-only even when a newer release exists (changed == 'true').
    writers = [s for s in STEPS if "peter-evans/create-pull-request@" in s or re.search(r"\bgh pr\b", s)]
    assert len(writers) == 2, "expected the pull request step and the auto-merge step"
    for step in writers:
        assert re.search(r"(?m)^\s*(?:- )?if:.*!inputs\.probe", step), "a step that writes must be skipped on a probe"


def test_probe_step_only_reads_and_checks_the_token_covers_this_repository_only():
    probe = [s for s in STEPS if re.search(r"(?m)^\s*if:\s*inputs\.probe\s*$", s)]
    assert len(probe) == 1, "expected exactly one probe step"
    assert re.search(r'gh api "repos/\$\{REPO\}"', probe[0])
    assert re.search(r"gh api installation/repositories", probe[0])
    assert re.search(r'test "\$\{covered\}" = "\$\{REPO\}"', probe[0]), "the probe must fail if the token covers more"
    # `gh api` turns into a POST as soon as it is given a field, so fields and bodies are as forbidden as -X, with
    # the value attached (-XPOST, -fname=value) or separate.
    writes = r"\bgh pr\b|\bgit\b|--method|\s-[XfF]|--field|--raw-field|--input"
    assert not re.search(writes, probe[0]), "the probe must not write"
