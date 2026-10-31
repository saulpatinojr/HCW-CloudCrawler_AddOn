"""Move the engine pin for core-update.yml, and check the lock that `uv lock` wrote for it.

The engine `cloud-crawler-core` is pinned in pyproject.toml by two lines that move together:

- the dependency line, the wheel's release-asset URL with the marker `CORE_REF <tag>` (pinned_line below builds it);
- the version line of the engine's static metadata, `version = "<version>"  # CORE_METADATA` (issue 33).

`bump` replaces both lines, each built exactly from the old tag, with the lines for the new tag. It is a plain string
replacement (no sed, no pattern language), so a tag cannot inject an edit or a command, and both tags must be
v<major>.<minor>.<patch> before anything is read. Either both lines are replaced or nothing is written.

`check-lock` reads the uv.lock that `uv lock` wrote after the bump and the default branch's uv.lock, and refuses
(exit 1) unless the only differences are the engine's: its version and URL, one wheel with a sha256, dependencies that
were already locked, the version of its static metadata, and the project's reference to its URL. core-update.yml's
pull-request job runs it on the lock it regenerated itself, before it mints the App token.

The script uses the standard library only, never touches the network and never imports the engine, so the
pull-request job can run it (from the default branch's checkout) without running any engine code.

Usage: python scripts/bump_core_pin.py bump --from v0.1.0 --tag v0.2.0 [--root <repository root>]
       python scripts/bump_core_pin.py check-lock --old <default branch's uv.lock> --new uv.lock --tag v0.2.0
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

UPSTREAM = "saulpatinojr/HCW-CloudCrawler_App"
ENGINE = "cloud-crawler-core"
PROJECT = "cloud-crawler-lab"
TAG = re.compile(r"v(\d+\.\d+\.\d+)")
SHA256 = re.compile(r"sha256:[0-9a-f]{64}")


class BumpError(RuntimeError):
    """The files did not look as expected; nothing was written (bump) or the lock is refused (check-lock)."""


def version_of(tag: str) -> str:
    match = TAG.fullmatch(tag)
    if not match:
        raise BumpError(f"tag {tag!r} is not v<major>.<minor>.<patch>")
    return match.group(1)


def wheel_url(tag: str) -> str:
    version = version_of(tag)
    return f"https://github.com/{UPSTREAM}/releases/download/{tag}/cloud_crawler_core-{version}-py3-none-any.whl"


def pinned_line(tag: str) -> str:
    return f'  "{ENGINE} @ {wheel_url(tag)}",  # CORE_REF {tag}'


def metadata_line(tag: str) -> str:
    return f'version = "{version_of(tag)}"  # CORE_METADATA'


def _replace_line(text: str, old: str, new: str, what: str) -> str:
    lines = text.split("\n")
    found = [i for i, line in enumerate(lines) if line == old]
    if len(found) != 1:
        raise BumpError(f"pyproject.toml: expected exactly one {what} line for the old tag, found {len(found)}")
    lines[found[0]] = new
    return "\n".join(lines)


def bump_pyproject(text: str, old_tag: str, new_tag: str) -> str:
    if version_of(old_tag) == version_of(new_tag):
        raise BumpError("the old and the new tag are the same")
    text = _replace_line(text, pinned_line(old_tag), pinned_line(new_tag), "CORE_REF")
    return _replace_line(text, metadata_line(old_tag), metadata_line(new_tag), "CORE_METADATA")


def bump(root: Path, old_tag: str, new_tag: str) -> Path:
    path = root / "pyproject.toml"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BumpError(f"pyproject.toml: {type(exc).__name__}") from None
    path.write_text(bump_pyproject(text, old_tag, new_tag), encoding="utf-8")
    return path


def _load(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise BumpError(f"{path.name} cannot be read as TOML: {type(exc).__name__}") from None


def _by_name(lock: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for package in lock.get("package", []):
        name = package.get("name")
        if not isinstance(name, str) or name in out:
            raise BumpError(f"{name!r} is locked twice or has no name")
        out[name] = package
    return out


def _engine_metadata(lock: dict) -> tuple[list, list]:
    """The engine's static-metadata entries in the lock's manifest, and every other entry."""
    entries = lock.get("manifest", {}).get("dependency-metadata", [])
    return [e for e in entries if e.get("name") == ENGINE], [e for e in entries if e.get("name") != ENGINE]


def check_lock(new: dict, old: dict, tag: str) -> str:
    """Refuse a lock in which anything but the engine moved. Returns the engine wheel's hash."""
    version, url = version_of(tag), wheel_url(tag)
    # `revision` is the lock format's own revision number; it carries no dependency. Everything else in the header,
    # apart from the packages and the manifest (both checked below), must be the same.
    skip = ("package", "manifest", "revision")
    if {k: v for k, v in new.items() if k not in skip} != {k: v for k, v in old.items() if k not in skip}:
        raise BumpError("its header changed")
    if not isinstance(new.get("revision"), int):
        raise BumpError("its revision is not a number")
    if {k: v for k, v in new.get("manifest", {}).items() if k != "dependency-metadata"} != {
        k: v for k, v in old.get("manifest", {}).items() if k != "dependency-metadata"
    }:
        raise BumpError("its manifest changed")
    (new_meta, new_rest), (old_meta, old_rest) = _engine_metadata(new), _engine_metadata(old)
    if new_rest != old_rest or len(new_meta) != 1 or len(old_meta) != 1:
        raise BumpError("the static metadata of a package other than the engine changed")
    if new_meta[0].get("version") != version:
        raise BumpError("the engine's static metadata is not at the new version")
    if {k: v for k, v in new_meta[0].items() if k != "version"} != {
        k: v for k, v in old_meta[0].items() if k != "version"
    }:
        raise BumpError("the engine's static metadata changed beyond its version")

    n, o = _by_name(new), _by_name(old)
    for name in sorted(set(n) | set(o)):
        if name not in (ENGINE, PROJECT) and n.get(name) != o.get(name):
            raise BumpError(f"{name} changed, appeared or disappeared; only the engine moves in a bump")
    if ENGINE not in n or PROJECT not in n or PROJECT not in o:
        raise BumpError("the engine or the project is missing")
    engine = n[ENGINE]
    wheels = engine.get("wheels", [])
    if engine.get("version") != version or engine.get("source") != {"url": url}:
        raise BumpError("the engine is not the new version from the pinned URL")
    if "sdist" in engine or len(wheels) != 1 or wheels[0].get("url") != url:
        raise BumpError("the engine is not exactly one wheel from the pinned URL")
    digest = wheels[0].get("hash", "")
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        raise BumpError("the engine wheel has no sha256")
    for dep in engine.get("dependencies", []):
        if dep.get("name") not in o or dep.get("name") in (ENGINE, PROJECT):
            raise BumpError(f"the engine depends on {dep.get('name')!r}, which was not locked before")

    def without_engine_url(package: dict) -> dict:
        package = dict(package)
        metadata = dict(package.get("metadata", {}))
        metadata["requires-dist"] = [
            {k: v for k, v in d.items() if k != "url"} if d.get("name") == ENGINE else d
            for d in metadata.get("requires-dist", [])
        ]
        package["metadata"] = metadata
        return package

    if without_engine_url(n[PROJECT]) != without_engine_url(o[PROJECT]):
        raise BumpError("the project entry changed beyond the engine's URL")
    requires = [d for d in n[PROJECT].get("metadata", {}).get("requires-dist", []) if d.get("name") == ENGINE]
    if requires != [{"name": ENGINE, "url": url}]:
        raise BumpError("the project does not require the engine from the pinned URL exactly once")
    return digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("bump", help="move the CORE_REF and CORE_METADATA lines from one tag to another")
    one.add_argument("--from", dest="old_tag", required=True)
    one.add_argument("--tag", required=True)
    one.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    two = sub.add_parser("check-lock", help="refuse a lock in which anything but the engine moved")
    two.add_argument("--old", type=Path, required=True)
    two.add_argument("--new", type=Path, required=True)
    two.add_argument("--tag", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "bump":
            path = bump(args.root, args.old_tag, args.tag)
            print(f"rewrote {path.name}: {args.old_tag} -> {args.tag}")
        else:
            digest = check_lock(_load(args.new), _load(args.old), args.tag)
            print(f"uv.lock: only {ENGINE} moved, to {wheel_url(args.tag)} with {digest}")
    except BumpError as exc:
        what = "bump refused, nothing written" if args.command == "bump" else "uv.lock refused"
        print(f"::error::{what}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
