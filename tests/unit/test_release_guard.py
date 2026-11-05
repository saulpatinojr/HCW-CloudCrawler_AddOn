"""scripts/check_release_version.py: the permanent guard that a release tag, every version place and the changelog
agree, and that the dry run of `publish-images.yml` refuses everything the tag run would refuse. A v* tag publishes the
image and cannot be taken back, so these cases are the only chance to catch a wrong one. No network; the git cases
build a throwaway repository."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_release_version.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_release_version", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


guard = _load()

CHANGELOG = """# Changelog

## [Unreleased]

## [0.1.0] - 2026-10-25

### Added

- The first release.

## [0.0.9] - 2026-01-01

### Fixed

- Something older.
"""


def make_repo(root: Path, *, version: str = "0.1.0", changelog: str = CHANGELOG, **override: str) -> Path:
    """A minimal tree with the files the guard reads. `override` replaces one version by its label key."""
    versions = {"toml": version, "py": version, "lock": version}
    versions.update(override)
    files = {
        "pyproject.toml": f'[project]\nname = "cloud-crawler-lab"\nversion = "{versions["toml"]}"\n',
        "src/cloud_crawler_lab/__init__.py": f'"""x"""\n\n__version__ = "{versions["py"]}"\nADDON_ID = "x"\n',
        "uv.lock": (
            "version = 1\n\n"
            f'[[package]]\nname = "cloud-crawler-lab"\nversion = "{versions["lock"]}"\n\n'
            '[[package]]\nname = "cloud-crawler-core"\nversion = "0.1.1"\n\n'
            '[[package]]\nname = "pydantic"\nversion = "9.9.9"\n'
        ),
        "CHANGELOG.md": changelog,
    }
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def problems(root: Path, tag: str | None = None) -> list[str]:
    return guard.check(root, tag)[0]


def test_this_repository_is_consistent():
    found, errors = guard.read_versions(ROOT)
    assert errors == []
    assert len(found) == 3 and len(set(found.values())) == 1
    assert problems(ROOT) == []


def test_script_runs_as_a_program_and_succeeds_here():
    result = subprocess.run([sys.executable, "-I", str(SCRIPT)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.startswith("release version consistent: ")


def test_consistent_tree_passes(tmp_path):
    root = make_repo(tmp_path)
    assert guard.check(root) == ([], "0.1.0")
    assert problems(root, "v0.1.0") == []
    assert problems(root, "refs/tags/v0.1.0") == []


@pytest.mark.parametrize("which", ["toml", "py", "lock"])
def test_any_single_disagreeing_file_fails(tmp_path, which):
    root = make_repo(tmp_path, **{which: "0.1.1"})
    found = problems(root)
    assert found and "differs between files (0.1.0, 0.1.1)" in found[0]
    assert guard.check(root)[1] is None


@pytest.mark.parametrize("version", ["0.1.0rc1", "0.1.0-rc.1", "1.0", "01.2.3", "v0.1.0"])
def test_only_plain_x_y_z_is_a_release_version(tmp_path, version):
    root = make_repo(tmp_path, version=version)
    assert any("is not a plain X.Y.Z" in p for p in problems(root))


def test_missing_and_unreadable_sources_are_reported_not_raised(tmp_path):
    root = make_repo(tmp_path)
    (root / "src/cloud_crawler_lab/__init__.py").write_text("ADDON_ID = 'x'\n", encoding="utf-8")
    (root / "pyproject.toml").unlink()
    (root / "uv.lock").write_text("[[package]]\nname = 'pydantic'\nversion = '1'\n", encoding="utf-8")
    found = problems(root)
    assert any("no version found in src/cloud_crawler_lab/__init__.py" in p for p in found)
    assert any("cannot read pyproject.toml" in p for p in found)
    assert any("uv.lock has no entry for cloud-crawler-lab" in p for p in found)
    (root / "uv.lock").write_text("not [valid toml", encoding="utf-8")
    assert any("cannot read uv.lock" in p for p in problems(root))
    (root / "uv.lock").unlink()
    assert any("cannot read uv.lock" in p for p in problems(root))
    (root / "pyproject.toml").write_text("not [valid toml", encoding="utf-8")
    assert any("cannot read pyproject.toml" in p for p in problems(root))


@pytest.mark.parametrize("tag", ["v0.1.1", "0.1.0", "v0.1", "v0.1.0-rc.1", "release-1", "vtest", "v0.1.0 "])
def test_a_tag_that_is_not_v_plus_the_version_fails(tmp_path, tag):
    found = problems(make_repo(tmp_path), tag)
    assert any(f"tag {tag!r} is not v followed by X.Y.Z" in p or f"tag {tag} does not match" in p for p in found)


def test_changelog_must_have_a_dated_non_empty_section_for_a_tag(tmp_path):
    assert any(
        "no '## [0.1.0] - YYYY-MM-DD' section" in p
        for p in problems(make_repo(tmp_path, changelog="# Changelog\n"), "v0.1.0")
    )
    undated = CHANGELOG.replace("## [0.1.0] - 2026-10-25", "## [0.1.0]")
    assert any("has no release date" in p for p in problems(make_repo(tmp_path, changelog=undated), "v0.1.0"))
    baddate = CHANGELOG.replace("2026-10-25", "yesterday")
    assert any("has no release date" in p for p in problems(make_repo(tmp_path, changelog=baddate), "v0.1.0"))
    nodate = CHANGELOG.replace("2026-10-25", "2026-02-30")
    assert any("does not exist" in p for p in problems(make_repo(tmp_path, changelog=nodate), "v0.1.0"))
    future = CHANGELOG.replace("2026-10-25", "2999-01-01")
    assert any("is in the future" in p for p in problems(make_repo(tmp_path, changelog=future), "v0.1.0"))
    empty = CHANGELOG.replace("### Added\n\n- The first release.\n", "### Added\n")
    assert any("section for 0.1.0 is empty" in p for p in problems(make_repo(tmp_path, changelog=empty), "v0.1.0"))
    twice = CHANGELOG + "\n## [0.1.0] - 2026-10-26\n\n- again\n"
    assert any("more than once" in p for p in problems(make_repo(tmp_path, changelog=twice), "v0.1.0"))
    assert problems(make_repo(tmp_path, changelog=empty)) == []  # not a tag: the changelog is not required


def test_unreleased_entries_block_a_tag_but_not_ordinary_work(tmp_path):
    unreleased = CHANGELOG.replace("## [Unreleased]\n", "## [Unreleased]\n\n### Fixed\n\n- A late fix.\n")
    root = make_repo(tmp_path, changelog=unreleased)
    assert problems(root) == []
    assert any("still has entries under [Unreleased]" in p for p in problems(root, "v0.1.0"))
    only_headings = CHANGELOG.replace("## [Unreleased]\n", "## [Unreleased]\n\n### Fixed\n\n### Added\n")
    assert problems(make_repo(tmp_path, changelog=only_headings), "v0.1.0") == []
    bare = CHANGELOG.replace("## [Unreleased]\n", "## unreleased\n\n- A late fix.\n")
    assert any(
        "still has entries under [Unreleased]" in p for p in problems(make_repo(tmp_path, changelog=bare), "v0.1.0")
    )


def test_changelog_sections_ignore_headings_inside_code_fences_and_comments():
    text = (
        "## [1.0.0] - 2026-01-01\n\nText\n\n```markdown\n## [9.9.9] - 2030-01-01\n```\n\n"
        "<!--\n## [8.8.8] - 2030-01-01\n-->\n\n## Other heading\n\nhidden\n"
    )
    sections = guard.changelog_sections(text)
    assert list(sections) == ["1.0.0"]
    assert "9.9.9" in sections["1.0.0"][1] and "hidden" not in sections["1.0.0"][1]


def test_a_version_prefix_does_not_pick_the_wrong_section():
    text = "## [10.1.0] - 2026-01-01\n\n- ten\n\n## [0.1.0] - 2025-01-01\n\n- zero\n\n[0.1.0]: https://x.invalid\n"
    assert guard.changelog_sections(text)["0.1.0"] == ("2025-01-01", "- zero")


def test_notes_are_the_changelog_section(tmp_path, capsys):
    root = make_repo(tmp_path / "repo")
    notes = tmp_path / "notes.md"
    assert guard.main(["--root", str(root), "--tag", "v0.1.0", "--notes-out", str(notes)]) == 0
    assert notes.read_text(encoding="utf-8") == "### Added\n\n- The first release.\n"
    assert "tag v0.1.0" in capsys.readouterr().out


def test_notes_with_no_section_fail_and_write_nothing(tmp_path, capsys):
    root = make_repo(tmp_path / "repo", changelog="# Changelog\n")
    notes = tmp_path / "notes.md"
    assert guard.main(["--root", str(root), "--notes-out", str(notes)]) == 1
    assert not notes.exists()
    assert "missing or empty: there are no release notes" in capsys.readouterr().out


def test_a_plain_run_warns_about_unreleased_entries_but_still_writes_notes(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    unreleased = CHANGELOG.replace("## [Unreleased]\n", "## [Unreleased]\n\n- A late fix.\n")
    root = make_repo(tmp_path / "repo", changelog=unreleased)
    notes = tmp_path / "notes.md"
    assert guard.main(["--root", str(root), "--notes-out", str(notes)]) == 0
    assert notes.exists()
    assert "::warning::CHANGELOG.md still has entries under [Unreleased]" in capsys.readouterr().out


def test_failures_are_github_annotations_under_actions_and_plain_lines_otherwise(tmp_path, capsys, monkeypatch):
    root = make_repo(tmp_path, py="0.2.0")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert guard.main(["--root", str(root)]) == 1
    assert capsys.readouterr().out.startswith("::error::the version differs between files")
    monkeypatch.delenv("GITHUB_ACTIONS")
    assert guard.main(["--root", str(root)]) == 1
    assert capsys.readouterr().out.startswith("error: the version differs between files")


def test_a_stale_release_date_is_a_warning_not_a_refusal(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    root = make_repo(tmp_path, changelog=CHANGELOG.replace("2026-10-25", "2020-01-01"))
    assert guard.main(["--root", str(root), "--tag", "v0.1.0"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("warning: the CHANGELOG.md section for 0.1.0 is dated 2020-01-01")


needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def git(directory: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false", *args],
        cwd=directory,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@needs_git
def test_only_a_commit_on_the_protected_branch_may_be_released(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "main commit")
    on_main = git(root, "rev-parse", "HEAD")
    git(root, "switch", "-q", "-c", "feature")
    (root / "extra.txt").write_text("unreviewed", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "feature commit")
    on_feature = git(root, "rev-parse", "HEAD")
    assert guard.on_branch(on_main, "main", root) is None
    assert "is not on main" in guard.on_branch(on_feature, "main", root)
    assert "could not compare" in guard.on_branch(on_main, "no-such-branch", root)

    monkeypatch.setenv("GITHUB_SHA", on_feature)
    assert guard.main(["--root", str(root), "--tag", "v0.1.0", "--ancestor-of", "main"]) == 1
    monkeypatch.setenv("GITHUB_SHA", on_main)
    assert guard.main(["--root", str(root), "--tag", "v0.1.0", "--ancestor-of", "main"]) == 0
    monkeypatch.delenv("GITHUB_SHA")
    git(root, "switch", "-q", "main")
    assert guard.main(["--root", str(root), "--tag", "v0.1.0", "--ancestor-of", "main"]) == 0


def git_repo(root: Path) -> Path:
    """`root` committed on `main`, so the rehearsal's tag lookup has a repository to ask."""
    git(root, "init", "-q", "-b", "main")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "main commit")
    return root


def errors(capsys) -> list[str]:
    return [line for line in capsys.readouterr().out.splitlines() if line.startswith("error: ")]


@needs_git
def test_rehearse_derives_the_tag_and_runs_every_tag_check(tmp_path, capsys, monkeypatch):
    """The dry run before a tag must be red for everything the tag would be refused for. A sister repository's tag was
    refused for entries under [Unreleased] after a green dry run that never read the changelog; the tag could not be
    taken back."""
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    root = git_repo(make_repo(tmp_path / "ok"))
    assert guard.main(["--root", str(root), "--rehearse"]) == 0
    assert "release version consistent: 0.1.0, tag v0.1.0" in capsys.readouterr().out
    bad = {
        "missing section": "# Changelog\n\n## [Unreleased]\n",
        "undated": CHANGELOG.replace(" - 2026-10-25", ""),
        "empty section": CHANGELOG.replace("### Added\n\n- The first release.\n", ""),
        "unreleased entries": CHANGELOG.replace("## [Unreleased]\n", "## [Unreleased]\n\n### Fixed\n\n- A late fix.\n"),
    }
    for label, text in bad.items():
        root = git_repo(make_repo(tmp_path / label.replace(" ", "-"), changelog=text))
        assert guard.main(["--root", str(root), "--rehearse"]) == 1, label
        rehearsal = errors(capsys)
        assert guard.main(["--root", str(root), "--tag", "v0.1.0"]) == 1, f"{label}: the tag run must refuse it too"
        assert rehearsal and rehearsal == errors(capsys), f"{label}: the dry run and the tag run must say the same"
    assert any("still has entries under [Unreleased]" in line for line in rehearsal)


def test_rehearse_is_red_for_a_disagreeing_version_and_is_never_a_second_way_to_pick_the_tag(tmp_path, capsys):
    root = make_repo(tmp_path / "repo", py="0.2.0")
    assert guard.main(["--root", str(root), "--rehearse"]) == 1
    assert "the version differs between files" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        guard.main(["--root", str(root), "--rehearse", "--tag", "v0.1.0"])


@needs_git
def test_rehearse_checks_ancestry_and_that_the_tag_is_still_free(tmp_path, monkeypatch, capsys):
    root = git_repo(make_repo(tmp_path))
    on_main = git(root, "rev-parse", "HEAD")
    git(root, "switch", "-q", "-c", "feature")
    (root / "extra.txt").write_text("unreviewed", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "feature commit")
    on_feature = git(root, "rev-parse", "HEAD")
    monkeypatch.setenv("GITHUB_SHA", on_main)
    assert guard.main(["--root", str(root), "--rehearse", "--ancestor-of", "main"]) == 0
    monkeypatch.setenv("GITHUB_SHA", on_feature)
    assert guard.main(["--root", str(root), "--rehearse", "--ancestor-of", "main"]) == 1
    assert "is not on main" in capsys.readouterr().out
    monkeypatch.setenv("GITHUB_SHA", on_main)
    git(root, "tag", "-a", "v0.1.0", on_main, "-m", "already released, or burned")
    assert guard.main(["--root", str(root), "--rehearse", "--ancestor-of", "main"]) == 1
    assert "the tag v0.1.0 already exists" in capsys.readouterr().out
    # the real tag run is the one that creates the tag, so the existing tag is not an error there
    assert guard.main(["--root", str(root), "--tag", "v0.1.0", "--ancestor-of", "main"]) == 0


@needs_git
def test_rehearse_reports_a_tag_lookup_that_cannot_be_made(tmp_path, capsys):
    root = make_repo(tmp_path)  # a directory that is not a git repository
    assert guard.main(["--root", str(root), "--rehearse"]) == 1
    assert "could not look up the tag v0.1.0" in capsys.readouterr().out


def test_health_reports_the_release_version_the_guard_holds_together(client):
    """/api/health and the X-Addon-Version header come from `__version__`; the guard keeps that constant equal to
    pyproject.toml and uv.lock, so the number the website's status proxy reads is the number of the tag and image."""
    import tomllib

    from cloud_crawler_lab import __version__

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    assert __version__ == pyproject == guard.check(ROOT)[1]
    health = client.get("/api/health")
    assert health.json()["version"] == pyproject and health.headers["x-addon-version"] == pyproject


def test_the_changelog_of_this_repository_is_readable_by_the_guard():
    sections = guard.changelog_sections((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
    assert "Unreleased" in sections
    released = {name: date for name, (date, _) in sections.items() if name != "Unreleased"}
    assert {"0.1.0", "0.2.0", "0.3.0"} <= set(released) and all(guard.DATE.match(d or "") for d in released.values())
