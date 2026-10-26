"""core-update.yml opens its bump pull request with a GitHub App token, never with GITHUB_TOKEN.

A pull request opened with GITHUB_TOKEN starts no workflow, so the required checks never run on it and it can never
merge. The App's credential lives in the admin-ops environment, hence the environment on the job. These are static
checks of the workflow text; they do not prove the credential works. A run with probe=true does (see the header of
the workflow)."""

import re

from ..conftest import ROOT

TEXT = (ROOT / ".github" / "workflows" / "core-update.yml").read_text(encoding="utf-8")
STEPS = re.split(r"(?m)^ {6}- ", TEXT.split("\njobs:\n", 1)[1])[1:]  # the steps of the one job
APP_TOKEN = r"\$\{\{\s*steps\.app-token\.outputs\.token\s*\}\}"


def _only(action: str) -> str:
    found = [s for s in STEPS if re.search(rf"(?m)^\s*uses:\s*{re.escape(action)}@", s)]
    assert len(found) == 1, f"expected exactly one step using {action}"
    return found[0]


def test_pull_request_is_opened_with_the_app_token_never_github_token():
    app = _only("actions/create-github-app-token")
    pr = _only("peter-evans/create-pull-request")
    assert re.search(r"(?m)^\s*id:\s*app-token\s*$", app)
    assert STEPS.index(app) < STEPS.index(pr), "the App token step must come before the pull request step"
    assert re.search(rf"(?m)^\s*token:\s*{APP_TOKEN}\s*$", pr)
    assert "GITHUB_TOKEN" not in pr, "create-pull-request must not be given GITHUB_TOKEN"


def test_every_step_that_runs_gh_pr_uses_the_app_token_after_it_was_minted():
    app = _only("actions/create-github-app-token")
    gh_pr = [s for s in STEPS if re.search(r"\bgh pr\b", s)]
    assert gh_pr, "the auto-merge step is missing"
    for step in gh_pr:
        assert re.search(rf"GH_TOKEN:\s*{APP_TOKEN}", step)
        assert STEPS.index(app) < STEPS.index(step)


def test_app_token_is_for_this_repository_only_with_contents_and_pull_requests_write():
    app = _only("actions/create-github-app-token")
    assert re.search(r"client-id:\s*\$\{\{\s*vars\.APP_CLIENT_ID\s*\}\}", app)
    assert re.search(r"private-key:\s*\$\{\{\s*secrets\.APP_PRIVATE_KEY\s*\}\}", app)
    granted = dict(re.findall(r"(?m)^\s*permission-([a-z-]+):\s*(\w+)\s*$", app))
    assert granted == {"contents": "write", "pull-requests": "write"}
    assert not re.search(r"(?m)^\s*(owner|repositories):", app), "owner or repositories would widen the token"


def test_job_runs_in_the_admin_ops_environment_which_holds_the_app_credential():
    assert re.search(r"(?m)^ {4}environment:\s*admin-ops\s*$", TEXT)


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


def test_probe_step_only_reads():
    probe = [s for s in STEPS if re.search(r"(?m)^\s*if:\s*inputs\.probe\s*$", s)]
    assert len(probe) == 1, "expected exactly one probe step"
    assert re.search(r'gh api "repos/\$\{REPO\}"', probe[0])
    assert not re.search(r"\bgh pr\b|\bgit\b|--method|\s-X\s", probe[0]), "the probe must not write"
