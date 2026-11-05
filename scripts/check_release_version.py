"""Check that every place that names this edition's version agrees, before a tag can make a mistake permanent.

Why this exists: a `v*` tag publishes the image (`publish-images.yml`) and cannot be taken back, so a tag that
disagrees with the version in the code, or a release whose notes are still under `[Unreleased]`, is a permanent
mistake. On 2026-11-04 a sister repository (HCW-CloudAssessor_App, pull request 88) burned a tag that way: its dry run
was green because it never read the changelog, and the tag run refused the same commit. This script runs the same checks
on the dry run and on the tag. Three modes, standard library only:

* Without `--tag` (CI's `lint` job, every pull request, `make lint`): `pyproject.toml`, `__version__` in
  `src/cloud_crawler_lab/__init__.py` and the `cloud-crawler-lab` entry of `uv.lock` must be the same plain `X.Y.Z`.
* With `--tag vX.Y.Z` (`publish-images.yml` on a tag): the same, plus the tag must be `v` + that version,
  `CHANGELOG.md` must have a dated (a real calendar date, not in the future), non-empty `## [X.Y.Z] - YYYY-MM-DD`
  section, no duplicate version heading, and an empty Unreleased section (`## [Unreleased]`, in any letter case, with
  or without the brackets), so the release notes are complete. With `--ancestor-of REF`, the tagged commit must already
  be on that branch (only reviewed commits are released).
* With `--rehearse` (`publish-images.yml` started by hand, the dry run before a tag): the tag is taken to be `v` + the
  package version and every check of the `--tag` mode runs, so the dry run is red for every state this script would
  refuse the tag for. Because there is no tag yet, it also fails when that tag already exists (a released or burned
  version must move on).

A release date that is valid but more than a week old only prints a warning (the release page would show it); the date
is refused only when it does not exist or is in the future.

`--notes-out FILE` writes the changelog section for the version (the release notes).

Exit 0 when everything agrees, 1 with one line per problem otherwise (GitHub `::error::` annotations under Actions).
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import os
import re
import subprocess  # nosec B404 - only runs git, with a fixed argument list and no shell
import sys
import tomllib
from pathlib import Path

VERSION = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
# `## [1.2.3] - 2026-10-25`, `## [Unreleased]` and bracket-less `## Unreleased`; any other `## ...` line ends a section
HEADING = re.compile(
    r"^##[ \t]+(?:\[(?P<bracketed>[^\]]+)\]|(?P<bare>(?i:unreleased)))"
    r"(?:[ \t]+-[ \t]+(?P<date>\S+))?[ \t]*$"
)
UNRELEASED = "Unreleased"
DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
FENCE = re.compile(r"^ {0,3}(?P<mark>`{3,}|~{3,})(?P<info>.*)$")
LINK_DEFINITION = re.compile(r"^ {0,3}\[[^\]]+\]:[ \t]*\S+.*$")
HTML_COMMENT = re.compile(r"<!--.*?(?:-->|\Z)", re.DOTALL)
# a release may be dated "today" in a time zone ahead of the runner's UTC clock, so one day ahead is tolerated
FUTURE_TOLERANCE = datetime.timedelta(days=1)
# an old date is only advisory: the release page would show it, so say so, but do not refuse the release
STALE_AFTER = datetime.timedelta(days=7)
DUNDER = re.compile(r'^__version__\s*=\s*"([^"]*)"\s*$', re.M)
PACKAGE = "cloud-crawler-lab"
SOURCES = {
    "pyproject.toml": "pyproject.toml",
    "__version__": "src/cloud_crawler_lab/__init__.py",
}
LOCK_LABEL = "uv.lock entry"


def read_versions(root: Path) -> tuple[dict[str, str], list[str]]:
    """Return {where: version} for every source that could be read, and a list of problems for those that could not."""
    found: dict[str, str] = {}
    problems: list[str] = []
    for label, relative in SOURCES.items():
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as error:
            problems.append(f"cannot read {relative} ({label}): {error.strerror or error}")
            continue
        if relative.endswith(".toml"):
            try:
                version = tomllib.loads(text).get("project", {}).get("version")
            except tomllib.TOMLDecodeError as error:
                problems.append(f"cannot read {relative} ({label}): {error}")
                continue
        else:
            match = DUNDER.search(text)
            version = match.group(1) if match else None
        if isinstance(version, str) and version:
            found[label] = version
        else:
            problems.append(f"no version found in {relative} ({label})")
    try:
        lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        problems.append(f"cannot read uv.lock: {error}")
        return found, problems
    packages = {p.get("name"): p.get("version") for p in lock.get("package", [])}
    if packages.get(PACKAGE):
        found[LOCK_LABEL] = packages[PACKAGE]
    else:
        problems.append(f"uv.lock has no entry for {PACKAGE} ({LOCK_LABEL})")
    return found, problems


def parse_changelog(text: str) -> tuple[dict[str, tuple[str | None, str]], list[str]]:
    """Map each release heading to (date, body), and list the headings that appear more than once.

    A release heading is `## [name]` (optionally ` - date`), or `## Unreleased` without brackets; Unreleased is matched
    in any letter case and always stored under the key "Unreleased". Headings inside code fences (backticks or tildes,
    as CommonMark closes them) and inside HTML comments are ignored. Trailing link reference definitions
    (`[0.1.0]: https://...`) are not part of the last section's body. The first of two equal headings is kept; the
    duplicate is reported, never silently preferred."""
    sections: dict[str, tuple[str | None, list[str]]] = {}
    duplicates: list[str] = []
    current: list[str] | None = None
    fence: tuple[str, int] | None = None
    in_comment = False
    for line in text.splitlines():
        if in_comment:
            in_comment = "-->" not in line
            if current is not None:
                current.append(line)
            continue
        opened = FENCE.match(line)
        if fence is not None:
            if (
                opened
                and opened["mark"][0] == fence[0]
                and len(opened["mark"]) >= fence[1]
                and not opened["info"].strip()
            ):
                fence = None
            if current is not None:
                current.append(line)
            continue
        if opened and not (opened["mark"][0] == "`" and "`" in opened["info"]):
            fence = (opened["mark"][0], len(opened["mark"]))
            if current is not None:
                current.append(line)
            continue
        if "<!--" in line and "-->" not in line.rsplit("<!--", 1)[1]:
            in_comment = True
        match = HEADING.match(line)
        if match:
            bare = match["bare"]
            name = (
                UNRELEASED
                if bare or match["bracketed"].strip().casefold() == UNRELEASED.casefold()
                else match["bracketed"]
            )
            if name in sections:
                duplicates.append(name)
                current = None
            else:
                current = []
                sections[name] = (match["date"], current)
        elif line.startswith("## "):
            current = None
        elif current is not None:
            current.append(line)
    bodies = {name: (date, _trim(body)) for name, (date, body) in sections.items()}
    return bodies, sorted(set(duplicates))


def _trim(body: list[str]) -> str:
    """The section text without the blank lines around it and without trailing link reference definitions."""
    lines = list(body)
    while lines and (not lines[-1].strip() or LINK_DEFINITION.match(lines[-1])):
        lines.pop()
    return "\n".join(lines).strip("\n")


def changelog_sections(text: str) -> dict[str, tuple[str | None, str]]:
    """Map each release heading to (date, body); see `parse_changelog`, which also reports duplicate headings."""
    return parse_changelog(text)[0]


def has_content(body: str) -> bool:
    """True when a section holds more than empty sub-headings (`### Fixed` with nothing under it is not content).

    HTML comments and link reference definitions are not content either: they render as nothing."""
    visible = HTML_COMMENT.sub("", body)
    return any(
        line.strip() and not line.startswith("#") and not LINK_DEFINITION.match(line) for line in visible.splitlines()
    )


def release_date_problem(date: str | None, version: str, today: datetime.date) -> str | None:
    """None when `date` is a real calendar date that is not in the future, otherwise the reason it is refused."""
    if not date or not DATE.match(date):
        return f"the CHANGELOG.md section for {version} has no release date (found {date!r})"
    try:
        released = datetime.date.fromisoformat(date)
    except ValueError:
        return f"the CHANGELOG.md section for {version} has a date that does not exist ({date})"
    if released > today + FUTURE_TOLERANCE:
        return f"the CHANGELOG.md section for {version} is dated {date}, which is in the future (today is {today})"
    return None


def stale_date_warning(root: Path, version: str, today: datetime.date) -> str | None:
    """A sentence when the release date is a valid one that is more than STALE_AFTER old, otherwise None."""
    try:
        date = parse_changelog((root / "CHANGELOG.md").read_text(encoding="utf-8"))[0].get(version, (None, ""))[0]
        released = datetime.date.fromisoformat(date) if date and DATE.match(date) else None
    except OSError, ValueError:
        return None
    if released is None or today - released <= STALE_AFTER:
        return None
    return (
        f"the CHANGELOG.md section for {version} is dated {date}, {(today - released).days} days ago: the release page "
        "will show that date. Change it to the day you tag, or leave it if it is right"
    )


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603 B607 - git by name, arguments are a fixed list, no shell
        ["git", *args], cwd=root, capture_output=True, text=True, check=False
    )


def on_branch(sha: str, ref: str, root: Path) -> str | None:
    """None when `sha` is an ancestor of `ref`, otherwise the reason it is not."""
    result = _git(root, "merge-base", "--is-ancestor", sha, ref)
    if result.returncode == 0:
        return None
    if result.returncode == 1:
        return f"commit {sha[:12]} is not on {ref}: release only commits that reached the protected branch"
    return f"could not compare {sha[:12]} with {ref}: {result.stderr.strip() or 'git failed'}"


def utc_today() -> datetime.date:
    return datetime.datetime.now(datetime.UTC).date()


def tag_exists(tag: str, root: Path) -> str | None:
    """None when no tag of that name exists here, otherwise the reason the rehearsal must stop."""
    result = _git(root, "rev-parse", "--quiet", "--verify", f"refs/tags/{tag}")
    if result.returncode == 0:
        return (
            f"the tag {tag} already exists: this version was released (or burned); raise the version everywhere first"
        )
    if result.returncode == 1:
        return None
    return f"could not look up the tag {tag}: {result.stderr.strip() or 'git failed'}"


def check(root: Path, tag: str | None = None, *, today: datetime.date | None = None) -> tuple[list[str], str | None]:
    """Return (problems, version). `version` is None when the sources disagree so much that none can be trusted."""
    versions, problems = read_versions(root)
    distinct = sorted(set(versions.values()))
    if len(distinct) > 1:
        for label, version in versions.items():
            problems.append(f"{label} says {version}")
        problems.insert(0, f"the version differs between files ({', '.join(distinct)})")
    version = distinct[0] if len(distinct) == 1 else None
    if version is not None and not VERSION.match(version):
        problems.append(f"version {version!r} is not a plain X.Y.Z (pre-release tags are not supported here)")
        version = None
    if tag is not None:
        tag = tag.removeprefix("refs/tags/")
        if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag):
            problems.append(f"tag {tag!r} is not v followed by X.Y.Z")
        elif version is not None and tag != f"v{version}":
            problems.append(f"tag {tag} does not match the package version {version}")
    if version is not None and tag is not None:
        problems.extend(changelog_problems(root, version, today or utc_today()))
    return problems, version


def changelog_problems(root: Path, version: str, today: datetime.date) -> list[str]:
    """Everything in CHANGELOG.md that would make the release notes for `version` wrong or incomplete."""
    try:
        sections, duplicates = parse_changelog((root / "CHANGELOG.md").read_text(encoding="utf-8"))
    except OSError as error:
        return [f"cannot read CHANGELOG.md: {error.strerror or error}"]
    problems = [
        f"CHANGELOG.md has the heading '## [{name}]' more than once: which one is the release?" for name in duplicates
    ]
    date, body = sections.get(version, (None, ""))
    if version not in sections:
        problems.append(f"CHANGELOG.md has no '## [{version}] - YYYY-MM-DD' section")
    elif (reason := release_date_problem(date, version, today)) is not None:
        problems.append(reason)
    elif not has_content(body):
        problems.append(f"the CHANGELOG.md section for {version} is empty")
    if UNRELEASED in sections and has_content(sections[UNRELEASED][1]):
        problems.append("CHANGELOG.md still has entries under [Unreleased]: fold them into the release section")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    which = parser.add_mutually_exclusive_group()
    which.add_argument("--tag", help="the tag being released, for example v0.3.0 (refs/tags/ prefix allowed)")
    which.add_argument(
        "--rehearse",
        action="store_true",
        help="dry run: take the tag to be v + the package version and run every check a real tag runs",
    )
    parser.add_argument("--notes-out", type=Path, help="write the changelog section for the version to this file")
    parser.add_argument(
        "--ancestor-of", metavar="REF", help="with --tag or --rehearse: the commit must be reachable from REF"
    )
    args = parser.parse_args(argv)
    tag = args.tag
    if args.rehearse:
        version = check(args.root)[1]
        tag = f"v{version}" if version else None
    problems, version = check(args.root, tag)
    if args.rehearse and version and (reason := tag_exists(f"v{version}", args.root)):
        problems.append(reason)
    if tag and args.ancestor_of and version:
        sha = os.environ.get("GITHUB_SHA") or _git(args.root, "rev-parse", "HEAD").stdout.strip()
        reason = on_branch(sha, args.ancestor_of, args.root)
        if reason:
            problems.append(reason)
    sections: dict[str, tuple[str | None, str]] = {}
    if (args.notes_out or not tag) and version:
        # an unreadable file: with a tag, check() reported it; without one, the missing notes are reported below
        with contextlib.suppress(OSError):
            sections = changelog_sections((args.root / "CHANGELOG.md").read_text(encoding="utf-8"))
    if args.notes_out and version:
        body = sections.get(version, (None, ""))[1]
        if has_content(body):
            args.notes_out.write_text(body + "\n", encoding="utf-8")
        elif not any("CHANGELOG.md" in p for p in problems):
            problems.append(f"the CHANGELOG.md section for {version} is missing or empty: there are no release notes")
    github = os.environ.get("GITHUB_ACTIONS") == "true"
    if tag and version and not problems and (stale := stale_date_warning(args.root, version, utc_today())):
        print(f"::warning::{stale}" if github else f"warning: {stale}")
    if args.notes_out and not tag and version and UNRELEASED in sections and has_content(sections[UNRELEASED][1]):
        warning = "CHANGELOG.md still has entries under [Unreleased]; a real tag is refused until they are folded in"
        print(f"::warning::{warning}" if github else f"warning: {warning}")
    for problem in problems:
        print(f"::error::{problem}" if github else f"error: {problem}")
    if problems:
        return 1
    tagged = f", tag {tag.removeprefix('refs/tags/')}" if tag else ""
    print(f"release version consistent: {version}{tagged}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
