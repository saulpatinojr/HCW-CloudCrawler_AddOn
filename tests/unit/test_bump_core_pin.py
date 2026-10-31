"""scripts/bump_core_pin.py and the core-update.yml steps around it, run against copies of this repository's files.

A real bump only happens on GitHub when the App tags a new release. Until then these tests make sure, in every pull
request, that the script still finds the two lines it moves (so that run does not fail on a stale exact match), that it
refuses anything but plain release tags, and that the pull-request job's apply step, run exactly as written in the
workflow, takes an artifact the bump job's own steps produced and refuses every tampered one with the checkout left
as it was. `uv lock` is replaced by a stand-in that edits uv.lock the way a real lock of a new release does, so no test
reaches the network.
"""

import hashlib
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tomllib

import pytest

from ..conftest import ROOT

SPEC = importlib.util.spec_from_file_location("bump_core_pin", ROOT / "scripts" / "bump_core_pin.py")
bump_core_pin = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bump_core_pin)

WORKFLOW = (ROOT / ".github" / "workflows" / "core-update.yml").read_text(encoding="utf-8")
NEW = "v99.0.0"
HOSTILE_TAGS = [
    "v9|;etouch${IFS}PWNED;#",
    "v1.0.0\nchanged=true",
    "v1.0.0 ",
    "v1.0",
    "v1.0.0-rc.1",
    "1.0.0",
    "v1.0.0;id",
    "",
]


def _run_block(marker: str) -> str:
    """The `run: |` script of the one step whose header holds `marker` (for example `id: apply`), dedented."""
    lines = WORKFLOW.splitlines()
    starts = [i for i, line in enumerate(lines) if line.strip().removeprefix("- ") == marker]
    assert len(starts) == 1, f"expected one step with {marker!r} in core-update.yml"
    i = starts[0]
    while lines[i].strip() != "run: |":
        assert not lines[i + 1].startswith("      - "), f"the step with {marker!r} has no run block"
        i += 1
    body = []
    for line in lines[i + 1 :]:
        if line.strip() and not line.startswith(" " * 10):
            break
        body.append(line[10:])
    return "\n".join(body) + "\n"


def _current_ref(root) -> str:
    """The `current=` line of the refs step, run as written."""
    line = next(ln.strip() for ln in _run_block("id: refs").splitlines() if ln.strip().startswith('current="$(grep'))
    out = subprocess.run(["bash", "-c", f'{line}\necho "$current"'], cwd=root, capture_output=True, text=True)
    return out.stdout.strip()


CURRENT = _current_ref(ROOT)

# --- the script on its own ---------------------------------------------------------------------------------------


def _pyproject():
    return (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_the_pin_has_the_two_lines_the_script_moves():
    text = _pyproject()
    assert re.fullmatch(r"v\d+\.\d+\.\d+", CURRENT), CURRENT
    assert text.splitlines().count(bump_core_pin.pinned_line(CURRENT)) == 1
    assert text.splitlines().count(bump_core_pin.metadata_line(CURRENT)) == 1


def test_bump_moves_exactly_the_two_lines(tmp_path):
    shutil.copy(ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    assert bump_core_pin.main(["bump", "--from", CURRENT, "--tag", NEW, "--root", str(tmp_path)]) == 0
    before, after = _pyproject().splitlines(), (tmp_path / "pyproject.toml").read_text(encoding="utf-8").splitlines()
    changed = [(a, b) for a, b in zip(before, after, strict=True) if a != b]
    assert changed == [
        (bump_core_pin.pinned_line(CURRENT), bump_core_pin.pinned_line(NEW)),
        (bump_core_pin.metadata_line(CURRENT), bump_core_pin.metadata_line(NEW)),
    ]
    assert 'releases/download/v99.0.0/cloud_crawler_core-99.0.0-py3-none-any.whl",  # CORE_REF v99.0.0' in "\n".join(
        after
    )
    assert _current_ref(tmp_path) == NEW
    # The result still parses and the metadata version is the new one.
    entry = tomllib.loads("\n".join(after))["tool"]["uv"]["dependency-metadata"][0]
    assert entry["name"] == "cloud-crawler-core" and entry["version"] == "99.0.0"


@pytest.mark.parametrize("tag", HOSTILE_TAGS)
def test_bump_refuses_a_hostile_tag_and_writes_nothing(tmp_path, tag):
    shutil.copy(ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    for args in (["--from", CURRENT, "--tag", tag], ["--from", tag, "--tag", NEW]):
        assert bump_core_pin.main(["bump", *args, "--root", str(tmp_path)]) == 1
    assert (tmp_path / "pyproject.toml").read_text(encoding="utf-8") == _pyproject()
    assert not list(tmp_path.rglob("PWNED"))


@pytest.mark.parametrize(
    "edit",
    [
        lambda t: t.replace("  # CORE_METADATA", "  # CORE-METADATA"),
        lambda t: t.replace("# CORE_REF", "#CORE_REF"),
        lambda t: t + bump_core_pin.metadata_line(CURRENT) + "\n",
        lambda t: t.replace(bump_core_pin.pinned_line(CURRENT), bump_core_pin.pinned_line(CURRENT) + " "),
    ],
    ids=["no-metadata-marker", "no-core-ref-marker", "metadata-twice", "pin-line-changed"],
)
def test_bump_refuses_a_pyproject_it_does_not_recognise_and_writes_nothing(tmp_path, edit):
    text = edit(_pyproject())
    (tmp_path / "pyproject.toml").write_text(text, encoding="utf-8")
    assert bump_core_pin.main(["bump", "--from", CURRENT, "--tag", NEW, "--root", str(tmp_path)]) == 1
    assert (tmp_path / "pyproject.toml").read_text(encoding="utf-8") == text


def test_bump_refuses_the_same_tag(tmp_path):
    shutil.copy(ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    assert bump_core_pin.main(["bump", "--from", CURRENT, "--tag", CURRENT, "--root", str(tmp_path)]) == 1


# --- a stand-in for `uv lock` -------------------------------------------------------------------------------------

# What a real `uv lock --no-build --upgrade-package cloud-crawler-core` does to uv.lock after the bump: the engine's
# version, URL and wheel hash move (in the package entry, the manifest and the project's requirement), nothing else.
# FAKE_UV_MODE makes it misbehave the same way in both jobs, so the files still match byte for byte and only the
# lock check can catch it. It refuses any other arguments, so a workflow that drops --no-build fails these tests too.
FAKE_UV = r"""#!{python}
import hashlib, os, re, sys
from pathlib import Path
args = sys.argv[1:]
if args != ["lock", "--no-build", "--upgrade-package", "cloud-crawler-core"]:
    sys.exit(f"stand-in uv: unexpected arguments {{args}}")
new_tag = re.search(r"# CORE_REF (v\S+)", Path("pyproject.toml").read_text()).group(1)
new_ver = new_tag[1:]
lock = Path("uv.lock").read_text()
old_ver = re.search(r'\[\[package\]\]\nname = "cloud-crawler-core"\nversion = "([^"]+)"', lock).group(1)
lock = lock.replace(f"/v{{old_ver}}/cloud_crawler_core-{{old_ver}}-", f"/{{new_tag}}/cloud_crawler_core-{{new_ver}}-")
entry = 'name = "cloud-crawler-core"\nversion = '
lock = lock.replace(f'{{entry}}"{{old_ver}}"', f'{{entry}}"{{new_ver}}"')
digest = "sha256:" + hashlib.sha256(new_tag.encode()).hexdigest()
lock = re.sub(r'(cloud_crawler_core-[^"]+\.whl", hash = ")sha256:[0-9a-f]{{64}}', lambda m: m.group(1) + digest, lock)
mode = os.environ.get("FAKE_UV_MODE", "")
if mode == "moves-another-package":
    lock = lock.replace('name = "fastapi"\nversion = "0.162.0"', 'name = "fastapi"\nversion = "0.162.1"')
elif mode == "no-hash":
    lock = lock.replace(digest, "md5:00")
elif mode == "new-dependency":
    engine_deps = r'(\[\[package\]\]\nname = "cloud-crawler-core"\n(?:.*\n)*?dependencies = \[\n)'
    lock = re.sub(engine_deps, r'\1    {{ name = "evil" }},\n', lock, count=1)
Path("uv.lock").write_text(lock)
"""


def test_the_stand_in_still_finds_what_it_edits():
    """Guards the stand-in itself: if the lock's layout moves, this fails before the apply tests can mislead.
    test_check_lock_accepts_a_lock_where_only_the_engine_moved proves its normal edit is what the lock check accepts."""
    old = (ROOT / "uv.lock").read_text(encoding="utf-8")
    assert 'name = "fastapi"\nversion = "0.162.0"' in old, "update FAKE_UV_MODE=moves-another-package"
    assert re.search(r'\[\[package\]\]\nname = "cloud-crawler-core"\n(?:.*\n)*?dependencies = \[\n', old)
    assert re.search(r'cloud_crawler_core-[^"]+\.whl", hash = "sha256:[0-9a-f]{64}', old)


# --- the pull-request job's apply step, as written ---------------------------------------------------------------


def _git(repo, *args):
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True, env=env)


def _tools(tmp_path):
    """A bin directory with the stand-in uv and this interpreter as `python`."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "uv").write_text(FAKE_UV.format(python=sys.executable))
    (bin_dir / "uv").chmod(0o755)
    (bin_dir / "python").symlink_to(sys.executable)
    return bin_dir


def _env(bin_dir, **extra):
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "GIT_CONFIG_GLOBAL": "/dev/null"}
    env.pop("FAKE_UV_MODE", None)
    env.update(extra)
    return env


def _status(repo) -> list[str]:
    return sorted(_git(repo, "status", "--porcelain").stdout.splitlines())


@pytest.fixture
def bump_run(tmp_path):
    """A clean checkout of this repository's bump files, and the artifact the bump job's own steps upload for it."""

    def make(mode: str = ""):
        repo, job_a, temp = tmp_path / "repo", tmp_path / "job-a", tmp_path / "temp"
        for name in ("pyproject.toml", "uv.lock", "scripts/bump_core_pin.py"):
            (repo / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / name, repo / name)
        (repo / "src").mkdir()
        (repo / "src" / "app.py").write_text("app\n")
        _git(repo, "init", "-q")
        _git(repo, "add", "-A")
        _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base")
        bin_dir = _tools(tmp_path)
        _git(tmp_path, "clone", "-q", str(repo), str(job_a))
        # The bump job: its bump step and its collect step, as written.
        env = _env(bin_dir, LATEST=NEW, CURRENT=CURRENT, FAKE_UV_MODE=mode)
        subprocess.run(["bash", "-c", _run_block("name: Bump CORE_REF and re-lock")], cwd=job_a, env=env, check=True)
        collect = _run_block("name: Collect the bump for the pull-request job")
        env = _env(bin_dir, RUNNER_TEMP=str(temp), COMPAT="success")
        subprocess.run(["bash", "-c", collect], cwd=job_a, env=env, check=True, capture_output=True)
        return repo, temp, temp / "bump", bin_dir

    return make


def _apply(repo, temp, bin_dir, latest=NEW, current=CURRENT, mode=""):
    output = temp / "github_output"
    output.write_text("")
    env = _env(bin_dir, RUNNER_TEMP=str(temp), GITHUB_OUTPUT=str(output), LATEST=latest, CURRENT=current)
    if mode:
        env["FAKE_UV_MODE"] = mode
    proc = subprocess.run(["bash", "-c", _run_block("id: apply")], cwd=repo, env=env, capture_output=True, text=True)
    return proc, output.read_text()


def test_the_apply_step_takes_a_bump_identical_to_its_own(bump_run):
    repo, temp, art, bin_dir = bump_run()
    assert sorted(p.name for p in art.iterdir()) == ["outcome", "pyproject.toml", "uv.lock"]
    proc, output = _apply(repo, temp, bin_dir)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert output == "outcome=success\n"
    assert "uv.lock: only cloud-crawler-core moved" in proc.stdout
    assert _status(repo) == [" M pyproject.toml", " M uv.lock"]
    for name in ("pyproject.toml", "uv.lock"):
        assert (repo / name).read_bytes() == (art / name).read_bytes()
    assert _current_ref(repo) == NEW


def test_the_apply_step_passes_a_failure_outcome_through_for_the_label(bump_run):
    repo, temp, art, bin_dir = bump_run()
    (art / "outcome").write_text("failure\n")
    proc, output = _apply(repo, temp, bin_dir)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert output == "outcome=failure\n"


def _append(path, text):
    path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")


def _symlink(art):
    (art / "uv.lock").unlink()
    (art / "uv.lock").symlink_to(ROOT / "uv.lock")


def _generated_doc(art):
    (art / "docs" / "rules").mkdir(parents=True)
    (art / "docs" / "rules" / "catalog.md").write_text("# Rule catalog\n")


TAMPERING = {
    "pyproject-extra-line": lambda art: _append(art / "pyproject.toml", 'evil = "yes"\n'),
    "pyproject-other-dependency": lambda art: (art / "pyproject.toml").write_text(
        (art / "pyproject.toml").read_text().replace('"fastapi==0.162.0"', '"fastapi==0.162.1"')
    ),
    "uv-lock-changed": lambda art: _append(art / "uv.lock", "# changed\n"),
    "uv-lock-other-hash": lambda art: (art / "uv.lock").write_text(
        re.sub(r"sha256:[0-9a-f]{64}", "sha256:" + "0" * 64, (art / "uv.lock").read_text(), count=1)
    ),
    "pyproject-missing": lambda art: (art / "pyproject.toml").unlink(),
    "extra-file": lambda art: (art / "run.sh").write_text("echo planted\n"),
    "generated-doc": _generated_doc,
    "empty-folder": lambda art: (art / "docs").mkdir(),
    "symlink": _symlink,
    "outcome-extra-line": lambda art: (art / "outcome").write_text("success\ncompat=true\n"),
    "outcome-no-newline": lambda art: (art / "outcome").write_text("success"),
    "outcome-blank-line": lambda art: (art / "outcome").write_text("success\n\n"),
    "outcome-other-word": lambda art: (art / "outcome").write_text("skipped\n"),
    "outcome-capitals": lambda art: (art / "outcome").write_text("SUCCESS\n"),
    "outcome-crlf": lambda art: (art / "outcome").write_text("success\r\n"),
    "no-outcome": lambda art: (art / "outcome").unlink(),
    "no-artifact": lambda art: shutil.rmtree(art),
}


@pytest.mark.parametrize("tamper", sorted(TAMPERING))
def test_the_apply_step_refuses_a_tampered_artifact_and_changes_nothing(bump_run, tamper):
    repo, temp, art, bin_dir = bump_run()
    TAMPERING[tamper](art)
    proc, output = _apply(repo, temp, bin_dir)
    assert proc.returncode == 1 and "::error::the bump artifact is refused" in proc.stdout, proc.stdout + proc.stderr
    assert output == "" and _status(repo) == []


@pytest.mark.parametrize("mode", ["moves-another-package", "no-hash", "new-dependency"])
def test_the_lock_check_refuses_a_lock_that_moves_more_than_the_engine(bump_run, mode):
    """Both jobs wrote the same wrong lock (a misbehaving locker), so only check-lock can catch it."""
    repo, temp, art, bin_dir = bump_run(mode)
    proc, output = _apply(repo, temp, bin_dir, mode=mode)
    assert proc.returncode == 1 and "moves more than the engine" in proc.stdout, proc.stdout + proc.stderr
    assert output == "" and _status(repo) == []


@pytest.mark.parametrize("which", ["latest", "current"])
@pytest.mark.parametrize("tag", ["v9|;etouch${IFS}PWNED;#", "v1.0.0\nchanged=true", "v1.0", ""])
def test_the_apply_step_refuses_a_malformed_tag(bump_run, which, tag):
    repo, temp, _, bin_dir = bump_run()
    tags = {"latest": NEW, "current": CURRENT, which: tag}
    proc, output = _apply(repo, temp, bin_dir, latest=tags["latest"], current=tags["current"])
    assert proc.returncode == 1 and output == "" and _status(repo) == [] and not list(repo.rglob("PWNED"))


def test_the_apply_step_refuses_a_bump_from_another_pin(bump_run):
    """A current tag that is not the checkout's pin: the exact replacement finds nothing and the step stops."""
    repo, temp, _, bin_dir = bump_run()
    proc, output = _apply(repo, temp, bin_dir, current="v0.0.1")
    assert proc.returncode == 1 and "does not apply" in proc.stdout and output == "" and _status(repo) == []


def test_the_apply_step_refuses_an_artifact_for_another_release(bump_run):
    """The bump job adopted v99.0.0; this job worked out v98.0.0 itself (for example a release appeared in between)."""
    repo, temp, _, bin_dir = bump_run()
    proc, output = _apply(repo, temp, bin_dir, latest="v98.0.0")
    assert proc.returncode == 1 and "differs from the one regenerated here" in proc.stdout
    assert output == "" and _status(repo) == []


# --- the lock check on its own ------------------------------------------------------------------------------------


def _locks(tmp_path, mode=""):
    """This repository's lock, and the lock the stand-in writes for a bump to NEW."""
    bin_dir = _tools(tmp_path)
    shutil.copy(ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    shutil.copy(ROOT / "uv.lock", tmp_path / "uv.lock")
    bump_core_pin.bump(tmp_path, CURRENT, NEW)
    env = _env(bin_dir, FAKE_UV_MODE=mode)
    subprocess.run(
        ["uv", "lock", "--no-build", "--upgrade-package", "cloud-crawler-core"], cwd=tmp_path, env=env, check=True
    )
    old = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    new = tomllib.loads((tmp_path / "uv.lock").read_text(encoding="utf-8"))
    return new, old


def test_check_lock_accepts_a_lock_where_only_the_engine_moved(tmp_path):
    new, old = _locks(tmp_path)
    assert bump_core_pin.check_lock(new, old, NEW) == "sha256:" + hashlib.sha256(NEW.encode()).hexdigest()


def _project(lock):
    return next(p for p in lock["package"] if p["name"] == "cloud-crawler-lab")


def _engine(lock):
    return next(p for p in lock["package"] if p["name"] == "cloud-crawler-core")


LOCK_TAMPERING = {
    "header": lambda new: new.update({"requires-python": ">=3.13"}),
    "revision-not-a-number": lambda new: new.update({"revision": "5"}),
    "manifest-extra": lambda new: new["manifest"].update({"overrides": [{"name": "pydantic"}]}),
    "metadata-old-version": lambda new: new["manifest"]["dependency-metadata"][0].update({"version": "0.1.0"}),
    "metadata-requires-dist": lambda new: new["manifest"]["dependency-metadata"][0].update({"requires-dist": []}),
    "engine-version": lambda new: _engine(new).update({"version": "98.0.0"}),
    "engine-source": lambda new: _engine(new).update({"source": {"url": "https://example.invalid/x.whl"}}),
    "engine-sdist": lambda new: _engine(new).update({"sdist": {"url": "https://example.invalid/x.tar.gz"}}),
    "engine-two-wheels": lambda new: _engine(new)["wheels"].append(dict(_engine(new)["wheels"][0])),
    "engine-depends-on-project": lambda new: _engine(new)["dependencies"].append({"name": "cloud-crawler-lab"}),
    "project-other-change": lambda new: _project(new).update({"version": "9.9.9"}),
    "project-old-url": lambda new: _project(new)["metadata"]["requires-dist"][0].update(
        {"url": bump_core_pin.wheel_url("v0.0.1")}
    ),
    "package-removed": lambda new: new.update({"package": [p for p in new["package"] if p["name"] != "fastapi"]}),
    "package-twice": lambda new: new["package"].append(dict(_engine(new))),
    "engine-removed": lambda new: new.update(
        {"package": [p for p in new["package"] if p["name"] != "cloud-crawler-core"]}
    ),
}


@pytest.mark.parametrize("tamper", sorted(LOCK_TAMPERING))
def test_check_lock_refuses_every_other_change(tmp_path, tamper):
    new, old = _locks(tmp_path)
    LOCK_TAMPERING[tamper](new)
    with pytest.raises(bump_core_pin.BumpError):
        bump_core_pin.check_lock(new, old, NEW)


def test_check_lock_refuses_a_wrong_tag_and_unreadable_files(tmp_path):
    new, old = _locks(tmp_path)
    with pytest.raises(bump_core_pin.BumpError):
        bump_core_pin.check_lock(new, old, "v98.0.0")
    (tmp_path / "bad.lock").write_text("not [toml")
    args = ["check-lock", "--old", str(ROOT / "uv.lock"), "--tag", NEW]
    assert bump_core_pin.main([*args, "--new", str(tmp_path / "bad.lock")]) == 1
    assert bump_core_pin.main([*args, "--new", str(tmp_path / "missing.lock")]) == 1
    assert bump_core_pin.main([*args, "--new", str(tmp_path / "uv.lock")]) == 0
