"""scripts/follow_website_base.py moves versions.env and every external FROM together, or nothing.

The script is what base-update.yml runs. It reads the website's pin as untrusted text, so each value must match a strict
pattern, and a Dockerfile it cannot move completely is left untouched.
"""

import ast
import importlib.util
import re
from pathlib import Path

import pytest

# Computed from this file's place, not imported from conftest, so the file is the same in every add-on repository.
ROOT = Path(__file__).resolve().parents[2]

_spec = importlib.util.spec_from_file_location("follow_website_base", ROOT / "scripts" / "follow_website_base.py")
assert _spec is not None and _spec.loader is not None
follow_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(follow_mod)

OLD = "sha256:" + "a" * 64
NEW = "sha256:" + "b" * 64
IMAGE = "python:3.14.8-slim-trixie"

VERSIONS = f"""# Base image comment that must survive the move.
BASE_IMAGE={IMAGE}
BASE_DIGEST={OLD}
BASE_PYTHON_VERSION=3.14.8
"""
DOCKERFILE = f"""# Header comment mentioning FROM {IMAGE}@{OLD} in prose is not a FROM line.
FROM {IMAGE}@{OLD} AS build
RUN true
FROM {IMAGE}@{OLD} AS lab
COPY --from=build /install /usr/local
FROM lab AS final
"""


def website(digest: str = NEW, image: str = IMAGE, version: str = "3.14.9") -> str:
    return f"# comment\nBASE_IMAGE={image}\nBASE_DIGEST={digest}\nBASE_PYTHON_VERSION={version}\nOTHER=1\n"


def make_repo(root: Path, versions: str = VERSIONS, dockerfile: str = DOCKERFILE) -> Path:
    docker = root / "infrastructure" / "docker"
    docker.mkdir(parents=True)
    (docker / "versions.env").write_text(versions, encoding="utf-8", newline="\n")
    (docker / "Dockerfile").write_text(dockerfile, encoding="utf-8", newline="\n")
    return root


def read(root: Path, name: str) -> str:
    return (root / "infrastructure" / "docker" / name).read_text(encoding="utf-8")


def test_moves_versions_env_and_every_external_from_together(tmp_path):
    root = make_repo(tmp_path)
    result = follow_mod.follow(root, website(), write=True)
    assert result["changed"] == "true"
    assert result["old"] == f"{IMAGE}@{OLD}"
    assert result["new"] == f"{IMAGE}@{NEW}"
    assert result["short"] == "b" * 12
    env = follow_mod.parse_env(read(root, "versions.env"))
    assert (env["BASE_IMAGE"], env["BASE_DIGEST"], env["BASE_PYTHON_VERSION"]) == (IMAGE, NEW, "3.14.9")
    assert read(root, "versions.env").startswith("# Base image comment that must survive the move.\n")
    froms = [line for line in read(root, "Dockerfile").splitlines() if line.startswith("FROM ")]
    assert froms == [f"FROM {IMAGE}@{NEW} AS build", f"FROM {IMAGE}@{NEW} AS lab", "FROM lab AS final"]
    assert OLD not in read(root, "Dockerfile").split("\n", 1)[1]  # only the prose comment on line 1 may mention it


def test_a_second_run_finds_nothing_to_do(tmp_path):
    root = make_repo(tmp_path)
    follow_mod.follow(root, website(), write=True)
    assert follow_mod.follow(root, website(), write=True) == {"changed": "false"}


def test_check_mode_reports_the_move_and_writes_nothing(tmp_path):
    root = make_repo(tmp_path)
    assert follow_mod.follow(root, website(), write=False)["changed"] == "true"
    assert read(root, "versions.env") == VERSIONS
    assert read(root, "Dockerfile") == DOCKERFILE


def test_nothing_to_do_when_the_pin_already_matches(tmp_path):
    root = make_repo(tmp_path)
    assert follow_mod.follow(root, website(digest=OLD, version="3.14.8"), write=True) == {"changed": "false"}


@pytest.mark.parametrize(
    "digest",
    [
        "sha256:" + "B" * 64,
        "sha256:" + "b" * 63,
        "sha256:" + "b" * 65,
        "b" * 64,
        "sha256:" + "b" * 63 + "z",
        "sha256:" + "b" * 64 + "\rBASE_IMAGE=evil:1",  # a lone carriage return must not start a second line
        "sha256:" + "b" * 64 + " ",
    ],
)
def test_a_digest_that_is_not_sha256_and_64_lowercase_hex_is_refused(tmp_path, digest):
    root = make_repo(tmp_path)
    with pytest.raises(follow_mod.FollowError):
        follow_mod.follow(root, website(digest=digest), write=True)
    assert read(root, "versions.env") == VERSIONS


@pytest.mark.parametrize(
    "image", ["python", "python:3.14;rm", "python:3 14", "Python:3.14", "$(id):3.14", "python:3.14$X", "", "-x:1"]
)
def test_an_image_that_is_not_name_colon_tag_is_refused(tmp_path, image):
    root = make_repo(tmp_path)
    with pytest.raises(follow_mod.FollowError):
        follow_mod.follow(root, website(image=image), write=True)
    assert read(root, "Dockerfile") == DOCKERFILE


@pytest.mark.parametrize("image", ["evil.example.com/team/python:3.14.9", "node:3.14.9-slim", "library/python:3.14.9"])
def test_a_different_image_repository_is_left_for_a_person_and_writes_nothing(tmp_path, image):
    root = make_repo(tmp_path)
    with pytest.raises(follow_mod.FollowError, match="a person must decide"):
        follow_mod.follow(root, website(image=image), write=True)
    assert (read(root, "versions.env"), read(root, "Dockerfile")) == (VERSIONS, DOCKERFILE)


def test_another_tag_of_the_same_repository_is_followed(tmp_path):
    root = make_repo(tmp_path)
    result = follow_mod.follow(root, website(image="python:3.14.9-slim-trixie", version="3.14.9"), write=True)
    assert result["new"] == f"python:3.14.9-slim-trixie@{NEW}"
    assert f"FROM python:3.14.9-slim-trixie@{NEW} AS build" in read(root, "Dockerfile")


def test_a_move_to_another_python_minor_line_is_left_for_a_person_and_writes_nothing(tmp_path):
    root = make_repo(tmp_path)
    with pytest.raises(follow_mod.FollowError, match="3.14 to 3.15"):
        follow_mod.follow(root, website(image="python:3.15.0-slim-trixie", version="3.15.0"), write=True)
    assert (read(root, "versions.env"), read(root, "Dockerfile")) == (VERSIONS, DOCKERFILE)


@pytest.mark.parametrize("version", ["3.14", "3.14.8-rc1", "v3.14.8", ""])
def test_a_python_version_that_is_not_major_minor_patch_is_refused(tmp_path, version):
    root = make_repo(tmp_path)
    with pytest.raises(follow_mod.FollowError):
        follow_mod.follow(root, website(version=version), write=True)


def test_a_website_file_without_the_keys_is_refused(tmp_path):
    root = make_repo(tmp_path)
    with pytest.raises(follow_mod.FollowError, match="missing"):
        follow_mod.follow(root, "BASE_IMAGE=python:3.14.8-slim-trixie\n", write=True)


def test_a_from_line_that_is_not_the_old_pin_stops_everything_and_writes_nothing(tmp_path):
    odd = DOCKERFILE.replace(f"FROM {IMAGE}@{OLD} AS lab", "FROM debian:trixie-slim AS lab")
    root = make_repo(tmp_path, dockerfile=odd)
    with pytest.raises(follow_mod.FollowError, match="neither an earlier stage"):
        follow_mod.follow(root, website(), write=True)
    assert read(root, "Dockerfile") == odd
    assert read(root, "versions.env") == VERSIONS


@pytest.mark.parametrize(
    "extra",
    [
        f"from {IMAGE}@{OLD} AS shout\n",  # lower-case FROM: ci.yml's grep ignores it, so it would be left behind
        f"ARG BASE={IMAGE}@{OLD}\n",
        f"COPY --from={IMAGE}@{OLD} /x /x\n",
        f"FROM --platform=linux/amd64 {IMAGE}@{OLD} AS plat\n",
    ],
)
def test_the_old_pin_left_anywhere_else_in_the_dockerfile_stops_everything(tmp_path, extra):
    odd = DOCKERFILE + extra
    root = make_repo(tmp_path, dockerfile=odd)
    with pytest.raises(follow_mod.FollowError):
        follow_mod.follow(root, website(), write=True)
    assert (read(root, "versions.env"), read(root, "Dockerfile")) == (VERSIONS, odd)


def test_a_dockerfile_with_no_from_on_the_old_pin_is_refused(tmp_path):
    root = make_repo(tmp_path, dockerfile="# no FROM lines\n")
    with pytest.raises(follow_mod.FollowError, match="no FROM line"):
        follow_mod.follow(root, website(), write=True)


def test_a_versions_env_that_repeats_a_key_is_refused(tmp_path):
    root = make_repo(tmp_path, versions=VERSIONS + f"BASE_DIGEST={OLD}\n")
    with pytest.raises(follow_mod.FollowError, match="exactly one"):
        follow_mod.follow(root, website(), write=True)
    assert read(root, "Dockerfile") == DOCKERFILE


@pytest.mark.parametrize("key", ["BASE_IMAGE", "BASE_DIGEST", "BASE_PYTHON_VERSION"])
def test_a_website_file_that_repeats_a_key_is_refused_because_two_readers_could_pick_different_lines(tmp_path, key):
    root = make_repo(tmp_path)
    repeated = website() + f"{key}={dict(BASE_IMAGE=IMAGE, BASE_DIGEST=NEW, BASE_PYTHON_VERSION='3.14.9')[key]}\n"
    with pytest.raises(follow_mod.FollowError, match="exactly one"):
        follow_mod.follow(root, repeated, write=True)
    assert (read(root, "versions.env"), read(root, "Dockerfile")) == (VERSIONS, DOCKERFILE)


def test_other_keys_in_the_website_file_may_repeat_or_look_similar(tmp_path):
    """The real website file has many other keys (SANDBOX_BASE_IMAGE, quoted blocks); only the three we read count."""
    root = make_repo(tmp_path)
    other_keys = [
        "SANDBOX_BASE_IMAGE=docker/sandbox-templates:claude-code",
        "OTHER=1",
        "OTHER=2",
        "ANSIBLE_CORE_DEPS='",
        "jinja2==3.1.6",
        "'",
    ]
    noisy = website() + "\n".join(other_keys) + "\n"
    assert follow_mod.follow(root, noisy, write=False)["changed"] == "true"


def test_when_only_the_python_version_line_differs_only_versions_env_moves(tmp_path):
    root = make_repo(tmp_path)
    result = follow_mod.follow(root, website(digest=OLD, version="3.14.9"), write=True)
    assert result["changed"] == "true" and result["old"] == result["new"] == f"{IMAGE}@{OLD}"
    assert follow_mod.parse_env(read(root, "versions.env"))["BASE_PYTHON_VERSION"] == "3.14.9"
    assert read(root, "Dockerfile") == DOCKERFILE


HOSTILE = [
    "${{ secrets.HCW_MAIN_ADMIN_PRIVATE_KEY }}",
    "$(id)",
    "`id`",
    "a b",
    "a\tb",
    "a'b",
    'a"b',
    "a;b",
    "a|b",
    "a&b",
    "a<b>",
    "a%0Ab",
    "[x](https://example.invalid)",
    "a\u2028b",
    "a^Eb",
    "a\x0bb",
    "a\x00b",
    "a\rb",
    "::set-output name=x::y",
]


@pytest.mark.parametrize("hostile", HOSTILE)
@pytest.mark.parametrize("key", ["BASE_IMAGE", "BASE_DIGEST", "BASE_PYTHON_VERSION"])
def test_a_hostile_value_in_the_website_file_is_refused_and_nothing_reaches_github_output(
    tmp_path, monkeypatch, capsys, key, hostile
):
    """Whatever the website file holds is data: it must not become a line of $GITHUB_OUTPUT, a workflow command, or pull
    request text, so every value is matched against a pattern that allows none of these characters."""
    root = make_repo(tmp_path / "repo")
    good = {"BASE_IMAGE": IMAGE, "BASE_DIGEST": NEW, "BASE_PYTHON_VERSION": "3.14.9"}
    for variant in (hostile, good[key] + hostile, hostile + good[key]):
        site = tmp_path / "website.env"
        site.write_bytes("".join(f"{k}={v}\n" for k, v in {**good, key: variant}.items()).encode("utf-8"))
        output = tmp_path / "github_output"
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        assert follow_mod.main(["--website-env", str(site), "--root", str(root)]) == 1
        printed = capsys.readouterr().out
        assert printed.startswith("::error::") and printed.count("\n") == 1, "one annotation, no echoed value"
        assert hostile not in printed
        assert not output.exists(), "nothing may be appended to $GITHUB_OUTPUT on a refusal"
        assert (read(root, "versions.env"), read(root, "Dockerfile")) == (VERSIONS, DOCKERFILE)


def test_every_value_written_to_github_output_is_one_safe_token(tmp_path, monkeypatch):
    root = make_repo(tmp_path / "repo")
    site = tmp_path / "website.env"
    site.write_text(website(), encoding="utf-8")
    output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert follow_mod.main(["--website-env", str(site), "--root", str(root), "--check"]) == 0
    lines = output.read_text(encoding="utf-8").split("\n")
    assert lines[-1] == "", "the file ends with one newline and no blank or extra line"
    pairs = [line.split("=", 1) for line in lines[:-1]]
    assert [key for key, _ in pairs] == ["changed", "old", "new", "short", "python", "old_python"]
    for _, value in pairs:
        assert re.fullmatch(r"[A-Za-z0-9._:@/-]+", value), f"{value!r} is not a safe single token"


def test_only_the_two_known_files_change_whatever_the_website_file_says(tmp_path):
    root = make_repo(tmp_path / "repo")
    (root / "other.txt").write_text("keep me\n", encoding="utf-8")

    def snapshot() -> dict[str, bytes]:
        return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}

    before = snapshot()
    follow_mod.follow(root, website(image="python:3.14.9-slim-trixie", version="3.14.9"), write=True)
    after = snapshot()
    changed = {name for name in before if before[name] != after.get(name)}
    assert changed == {"infrastructure/docker/versions.env", "infrastructure/docker/Dockerfile"}
    assert set(after) == set(before), "no file was added or removed"


def test_a_website_file_that_is_missing_or_not_utf8_text_ends_with_one_error_line(tmp_path, capsys):
    root = make_repo(tmp_path / "repo")
    assert follow_mod.main(["--website-env", str(tmp_path / "absent.env"), "--root", str(root)]) == 1
    assert capsys.readouterr().out.startswith("::error::")
    binary = tmp_path / "binary.env"
    binary.write_bytes(b"BASE_IMAGE=\xff\xfe\n")
    assert follow_mod.main(["--website-env", str(binary), "--root", str(root)]) == 1
    printed = capsys.readouterr().out
    assert printed.startswith("::error::") and printed.count("\n") == 1


@pytest.mark.parametrize(
    ("local", "reason"),
    [
        (
            "BASE_IMAGE=python:3.14.8-slim-trixie\nBASE_DIGEST=latest\nBASE_PYTHON_VERSION=3.14.8\n",
            "BASE_DIGEST is not",
        ),
        (
            f"BASE_IMAGE=python:3.14.8-slim-trixie\nBASE_DIGEST=sha256:{'A' * 64}\nBASE_PYTHON_VERSION=3.14.8\n",
            "BASE_DIGEST is not",
        ),
        (f"BASE_IMAGE=$(id):1\nBASE_DIGEST={OLD}\nBASE_PYTHON_VERSION=3.14.8\n", "BASE_IMAGE is not"),
        (f"BASE_IMAGE={IMAGE}\nBASE_DIGEST={OLD}\n", "missing BASE_PYTHON_VERSION"),
        ("", "missing"),
    ],
)
def test_this_repositorys_own_versions_env_is_validated_too_and_nothing_is_written(tmp_path, local, reason):
    """The refusal must come from reading the local file (its message names it), not from a later step by accident."""
    root = make_repo(tmp_path, versions=local)
    with pytest.raises(follow_mod.FollowError, match=reason) as caught:
        follow_mod.follow(root, website(), write=True)
    assert "infrastructure/docker/versions.env" in str(caught.value).replace("\\", "/")
    assert (read(root, "versions.env"), read(root, "Dockerfile")) == (local, DOCKERFILE)


def test_the_script_avoids_python_3_14_only_syntax_because_the_runners_own_python3_runs_it():
    """base-update.yml runs `python3 -I scripts/follow_website_base.py` with the runner's python3, not the project's
    3.14. Ruff's formatter rewrites `except (A, B):` into the bracket-less 3.14 form, which older Pythons cannot
    parse, so each exception class gets its own `except` clause."""
    source = (ROOT / "scripts" / "follow_website_base.py").read_text(encoding="utf-8")
    assert not re.search(r"(?m)^\s*except\s+[^(\n:]+,", source), "write one `except` clause per exception class"
    ast.parse(source, feature_version=(3, 9))


def test_compare_env_says_true_only_for_a_file_holding_exactly_the_websites_pin(tmp_path, monkeypatch, capsys):
    site = tmp_path / "website.env"
    site.write_text(website(), encoding="utf-8")
    output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    def compare(text: str | None) -> str:
        branch = tmp_path / "branch.env"
        branch.unlink(missing_ok=True)
        if text is not None:
            branch.write_text(text, encoding="utf-8")
        assert follow_mod.main(["--website-env", str(site), "--compare-env", str(branch)]) == 0
        return capsys.readouterr().out.strip()

    assert compare(website()) == "branch_current=true"
    assert compare(website() + "EXTRA=1\n") == "branch_current=true", "other keys do not matter"
    assert compare(website(digest=OLD)) == "branch_current=false", "an older digest"
    assert compare(website(version="3.14.8")) == "branch_current=false", "an older Python version"
    assert compare(website(image="python:3.14.9-slim-bookworm")) == "branch_current=false", "another tag"
    assert compare("BASE_IMAGE=oops\n") == "branch_current=false", "malformed"
    assert compare("") == "branch_current=false", "empty"
    assert compare(None) == "branch_current=false", "missing"
    assert output.read_text(encoding="utf-8").count("branch_current=") == 8


def test_compare_env_still_refuses_a_bad_website_file_and_writes_nothing_else(tmp_path, capsys):
    root = make_repo(tmp_path / "repo")
    site = tmp_path / "website.env"
    site.write_text(website(digest="not-a-digest"), encoding="utf-8")
    branch = tmp_path / "branch.env"
    branch.write_text(website(), encoding="utf-8")
    assert follow_mod.main(["--website-env", str(site), "--compare-env", str(branch), "--root", str(root)]) == 1
    assert capsys.readouterr().out.startswith("::error::")
    assert (read(root, "versions.env"), read(root, "Dockerfile")) == (VERSIONS, DOCKERFILE)


def test_compare_env_never_changes_this_repositorys_files(tmp_path):
    root = make_repo(tmp_path / "repo")
    site = tmp_path / "website.env"
    site.write_text(website(), encoding="utf-8")
    branch = tmp_path / "branch.env"
    branch.write_text(VERSIONS, encoding="utf-8")
    assert follow_mod.main(["--website-env", str(site), "--compare-env", str(branch), "--root", str(root)]) == 0
    assert (read(root, "versions.env"), read(root, "Dockerfile")) == (VERSIONS, DOCKERFILE)


def test_the_uv_image_and_other_digests_in_the_dockerfile_are_left_alone(tmp_path):
    """The real Dockerfiles also pull the uv image by digest; only the base image reference may move."""
    uv = "ghcr.io/astral-sh/uv:0.11.32@sha256:" + "c" * 64
    dockerfile = DOCKERFILE.replace(
        "RUN true\n", f"ARG EDITION=lab\nCOPY --from={uv} /uv /usr/local/bin/uv\nRUN true\n"
    )
    root = make_repo(tmp_path, dockerfile=dockerfile)
    follow_mod.follow(root, website(), write=True)
    moved = read(root, "Dockerfile")
    assert f"COPY --from={uv} /uv /usr/local/bin/uv" in moved
    assert moved.count(f"{IMAGE}@{NEW}") == 2


def test_a_crlf_versions_env_from_the_website_is_read_like_an_lf_one(tmp_path):
    root = make_repo(tmp_path)
    follow_mod.follow(root, website().replace("\n", "\r\n"), write=True)
    assert follow_mod.parse_env(read(root, "versions.env"))["BASE_DIGEST"] == NEW


def test_no_temporary_file_is_left_behind(tmp_path):
    root = make_repo(tmp_path)
    follow_mod.follow(root, website(), write=True)
    assert sorted(path.name for path in (root / "infrastructure" / "docker").iterdir()) == [
        "Dockerfile",
        "versions.env",
    ]


def test_a_crlf_dockerfile_keeps_its_line_endings(tmp_path):
    root = make_repo(tmp_path)
    path = root / "infrastructure" / "docker" / "Dockerfile"
    path.write_bytes(DOCKERFILE.replace("\n", "\r\n").encode("utf-8"))
    follow_mod.follow(root, website(), write=True)
    raw = path.read_bytes()
    assert raw.count(b"\r\n") == raw.count(b"\n") and NEW.encode() in raw


def test_each_file_keeps_its_own_line_endings(tmp_path):
    """A Windows checkout may hold CRLF in either file; the move must not turn one of them into LF."""
    root = make_repo(tmp_path)
    env_path = root / "infrastructure" / "docker" / "versions.env"
    env_path.write_bytes(VERSIONS.replace("\n", "\r\n").encode("utf-8"))
    follow_mod.follow(root, website(), write=True)
    raw = env_path.read_bytes()
    assert raw.count(b"\r\n") == raw.count(b"\n") and NEW.encode() in raw
    docker = (root / "infrastructure" / "docker" / "Dockerfile").read_bytes()
    assert b"\r" not in docker, "the LF Dockerfile stays LF"


def test_main_prints_the_result_and_appends_it_to_github_output(tmp_path, monkeypatch, capsys):
    root = make_repo(tmp_path / "repo")
    site = tmp_path / "website.env"
    site.write_text(website(), encoding="utf-8")
    output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert follow_mod.main(["--website-env", str(site), "--root", str(root)]) == 0
    printed = capsys.readouterr().out
    assert "changed=true" in printed and f"new={IMAGE}@{NEW}" in printed
    assert f"short={'b' * 12}" in output.read_text(encoding="utf-8")
    assert follow_mod.parse_env(read(root, "versions.env"))["BASE_DIGEST"] == NEW


def test_main_exits_nonzero_with_an_error_annotation_on_a_bad_website_file(tmp_path, capsys):
    root = make_repo(tmp_path / "repo")
    site = tmp_path / "website.env"
    site.write_text(website(digest="not-a-digest"), encoding="utf-8")
    assert follow_mod.main(["--website-env", str(site), "--root", str(root)]) == 1
    assert capsys.readouterr().out.startswith("::error::")


def test_this_repositorys_own_files_are_in_the_shape_the_script_can_move():
    """The real Dockerfile and versions.env: a different digest would move cleanly (check mode, nothing written)."""
    own = follow_mod.parse_env((ROOT / "infrastructure" / "docker" / "versions.env").read_text(encoding="utf-8"))
    assert follow_mod.follow(
        ROOT,
        website(digest=own["BASE_DIGEST"], image=own["BASE_IMAGE"], version=own["BASE_PYTHON_VERSION"]),
        write=False,
    ) == {"changed": "false"}
    moved = follow_mod.follow(
        ROOT, website(digest=NEW, image=own["BASE_IMAGE"], version=own["BASE_PYTHON_VERSION"]), write=False
    )
    assert moved["changed"] == "true" and moved["new"].endswith(NEW)
