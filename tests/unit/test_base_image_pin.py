"""infrastructure/docker/versions.env and every external FROM in the Dockerfile must name the same base image.

This is the pytest copy of the shell check in the `lint` job of ci.yml ("Base image digest in versions.env matches every
FROM in the Dockerfile"), so the rule is also enforced on a developer's computer and in the `test` job, and so a change
to either file that breaks it fails here with a plain message. It is written independently of
scripts/follow_website_base.py (which moves the pin): the last test here checks that what the script writes passes.

The rule: BASE_IMAGE@BASE_DIGEST from versions.env is `want`. Every FROM line must either start from an earlier stage of
the same Dockerfile (FROM lab AS final) or be exactly `want`. A Dockerfile with no FROM on `want` at all is also a
failure. This checker is a little stricter than ci.yml: it also sees a lower-case `from` and an indented FROM.
"""

import importlib.util
import re
from pathlib import Path

import pytest

# Computed from this file's place, not imported from conftest, so the file is the same in every add-on repository.
ROOT = Path(__file__).resolve().parents[2]
VERSIONS_ENV = ROOT / "infrastructure" / "docker" / "versions.env"
DOCKERFILE = ROOT / "infrastructure" / "docker" / "Dockerfile"


def disagreements(env_text: str, dockerfile_text: str) -> list[str]:
    values: dict[str, str] = {}
    for line in env_text.replace("\r\n", "\n").split("\n"):
        match = re.fullmatch(r"([A-Z][A-Z0-9_]*)=(.*)", line)
        if match:
            values[match.group(1)] = match.group(2)
    want = f"{values.get('BASE_IMAGE', '')}@{values.get('BASE_DIGEST', '')}"
    problems: list[str] = []
    if not re.fullmatch(r"[^@\s]+@sha256:[0-9a-f]{64}", want):
        problems.append(f"versions.env is not image@sha256:digest (BASE_IMAGE@BASE_DIGEST is {want!r})")
    stages: set[str] = set()
    on_want = 0
    for number, line in enumerate(dockerfile_text.replace("\r\n", "\n").split("\n"), start=1):
        parts = line.split()
        if len(parts) < 2 or parts[0].upper() != "FROM":
            continue
        reference = parts[1]
        if reference in stages:
            pass
        elif reference == want:
            on_want += 1
        else:
            problems.append(f"Dockerfile line {number}: FROM {reference} is neither an earlier stage nor {want}")
        if len(parts) >= 4 and parts[2].lower() == "as":
            stages.add(parts[3])
    if on_want == 0:
        problems.append(f"Dockerfile: no FROM line is {want}")
    return problems


ENV_TEXT = VERSIONS_ENV.read_text(encoding="utf-8")
DOCKER_TEXT = DOCKERFILE.read_text(encoding="utf-8")


def external_from_indexes(text: str) -> list[int]:
    """Zero-based line numbers of the FROM lines that name an image rather than an earlier stage."""
    stages: set[str] = set()
    found: list[int] = []
    for index, line in enumerate(text.replace("\r\n", "\n").split("\n")):
        parts = line.split()
        if len(parts) < 2 or parts[0].upper() != "FROM":
            continue
        if parts[1] not in stages:
            found.append(index)
        if len(parts) >= 4 and parts[2].lower() == "as":
            stages.add(parts[3])
    return found


EXTERNAL = external_from_indexes(DOCKER_TEXT)


def test_this_repositorys_versions_env_and_every_from_agree():
    assert disagreements(ENV_TEXT, DOCKER_TEXT) == []
    assert EXTERNAL, "the Dockerfile has no external FROM line; this test would prove nothing"


def _flip_last_hex_digit(digest_line: str) -> str:
    last = digest_line[-1]
    return digest_line[:-1] + ("0" if last != "0" else "1")


def test_it_fails_when_versions_env_moves_and_the_from_lines_do_not():
    moved = re.sub(r"(?m)^BASE_DIGEST=.*$", lambda m: _flip_last_hex_digit(m.group(0)), ENV_TEXT)
    assert moved != ENV_TEXT
    assert disagreements(moved, DOCKER_TEXT), "a different BASE_DIGEST must be reported"


def test_it_fails_when_the_tag_in_versions_env_moves_and_the_from_lines_do_not():
    moved = re.sub(r"(?m)^BASE_IMAGE=(.*)$", lambda m: m.group(0) + "-other", ENV_TEXT)
    assert moved != ENV_TEXT
    assert disagreements(moved, DOCKER_TEXT), "a different BASE_IMAGE must be reported"


@pytest.mark.parametrize("index", EXTERNAL)
def test_it_fails_when_any_single_external_from_line_differs(index):
    lines = DOCKER_TEXT.replace("\r\n", "\n").split("\n")
    parts = lines[index].split()
    parts[1] = _flip_last_hex_digit(parts[1])
    lines[index] = " ".join(parts)
    problems = disagreements(ENV_TEXT, "\n".join(lines))
    assert problems, f"the FROM on line {index + 1} was changed and nothing noticed"
    assert any(f"line {index + 1}" in problem for problem in problems), "the message names the line that differs"


def test_it_fails_when_a_from_names_another_image_or_there_is_no_from_on_the_pin():
    assert disagreements(ENV_TEXT, DOCKER_TEXT + "FROM debian:trixie-slim AS extra\n")
    assert disagreements(ENV_TEXT, "# no FROM lines at all\n")


def test_a_from_that_starts_from_an_earlier_stage_is_allowed():
    values = dict(re.findall(r"(?m)^([A-Z][A-Z0-9_]*)=(.*)$", ENV_TEXT))
    want = f"{values['BASE_IMAGE']}@{values['BASE_DIGEST']}"
    assert disagreements(ENV_TEXT, f"FROM {want} AS build\nFROM build AS final\n") == []
    assert disagreements(ENV_TEXT, f"FROM {want} AS build\nFROM builder AS final\n"), "an unknown stage is not allowed"


def test_it_fails_on_a_versions_env_that_is_not_image_at_digest():
    assert disagreements("BASE_IMAGE=python:3.14.8-slim-trixie\nBASE_DIGEST=latest\n", DOCKER_TEXT)
    assert disagreements("", DOCKER_TEXT)


def test_what_the_mover_writes_passes_this_check():
    """The script moves versions.env and every FROM together; the independent check above must agree it did."""
    spec = importlib.util.spec_from_file_location("follow_website_base", ROOT / "scripts" / "follow_website_base.py")
    assert spec is not None and spec.loader is not None
    follow_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(follow_mod)
    own = follow_mod.parse_env(ENV_TEXT)
    new_digest = "sha256:" + "d" * 64
    website = (
        f"BASE_IMAGE={own['BASE_IMAGE']}\nBASE_DIGEST={new_digest}\nBASE_PYTHON_VERSION={own['BASE_PYTHON_VERSION']}\n"
    )
    old_ref = f"{own['BASE_IMAGE']}@{own['BASE_DIGEST']}"
    new_ref = f"{own['BASE_IMAGE']}@{new_digest}"
    moved_docker = follow_mod.rewrite_dockerfile(DOCKER_TEXT.replace("\r\n", "\n"), old_ref, new_ref)
    moved_env = follow_mod.rewrite_versions_env(ENV_TEXT.replace("\r\n", "\n"), follow_mod.read_pin(website, "test"))
    assert disagreements(moved_env, moved_docker) == []
    assert disagreements(ENV_TEXT, moved_docker), "moving only the Dockerfile must be reported"
    assert disagreements(moved_env, DOCKER_TEXT), "moving only versions.env must be reported"
