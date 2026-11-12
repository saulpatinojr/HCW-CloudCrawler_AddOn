"""Every workflow job that runs Node.js or Python chooses its version (saulpatinojr/HCW-HybridCloudWorks#1707).

A job that runs `node`, `npm`, `npx`, `python3` or `pip` without actions/setup-node or actions/setup-python gets
whatever the runner image ships: on ubuntu-26.04 that was Node.js 24 and Python 3.14 in November 2026, both below the
program's floors (Node.js 26, Python 3.15). Nothing else notices, because a job that names no version has nothing to
read. This is a port of the website's check (scripts/workflow-runtime-setup.test.mjs in HCW-HybridCloudWorks).

A command counts when it is in command position on a line of a `run:` step: at the start, after `$(`, `<(`, `(`, `{`,
`|`, `&` or `;`, after leading `NAME=value` assignments, or after a word that runs the next one (`env`, `sudo`,
`xargs`, `exec`, `time`, `!`, `if`, `then`, `do` and the like). It does not count inside a quoted string or as an
argument (`docker run image python ...`). The set-up step must come before the first such step. Limits, on purpose:
a job that runs in a `container:` uses that image's runtime and is not checked; a script a step calls (a `.sh` file)
is not read; and a set-up step with its own `if:` counts as done, so give it the same condition as the steps that
need it.

The workflows are read with a small line reader rather than a YAML library, because none is a dependency here. It
relies on the layout every workflow in this repository has (a `jobs:` key at the top level, a `steps:` list, block
`run: |` scripts); a file it cannot read that way fails the test rather than being skipped.
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

import pytest

# Computed from this file's place, not imported from conftest, so the file is the same in every add-on repository.
ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"

# Steps that use the runner's own interpreter on purpose, each with its reason, keyed by
# "file > job > step name > runtime". Keyed by step, not job, so a new step in the same job is still checked. A new
# entry needs a reason a reviewer can check, and a comment above the step in the workflow saying the same.
RUNNER_DEFAULT_ALLOWED: dict[str, str] = {}

# Where a command may start: the line's start or an opening or joining character, then any `NAME=value` assignments
# and words that run the next word (`env FOO=1 node`, `sudo node`, `if node ...; then`).
START = (
    r"(?:^|[$<]\(\s*|[({|;&]\s*)"
    r"(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+|(?:env|sudo|xargs|exec|time|nice|command|if|then|else|elif|do|while|until|!)\s+)*"
)
COMMAND = {
    "node": re.compile(START + r"(?:node|npm|npx)(?=\s|$)"),
    "python": re.compile(START + r"(?:python(?:3(?:\.\d+)?)?|pip3?)(?=\s|$)"),
}
SETUP = {"node": re.compile(r"^actions/setup-node@"), "python": re.compile(r"^actions/setup-python@")}


def _without_quoted_text(line: str) -> str:
    """The line with the text of its quoted strings taken out, so words in a message (`echo "...; if pip named..."`)
    do not count. A double-quoted string that runs a command (`"$(node x)"`) is kept."""
    line = re.sub(r"'[^']*'", "''", line)
    return re.sub(r'"(?:[^"\\]|\\.)*"', lambda q: q.group(0) if re.search(r"[$<]\(", q.group(0)) else '""', line)


def runs_runtime(run: str | None, kind: str) -> bool:
    """True when a run script calls the runtime in command position on a line that is not a comment."""
    lines = (line.strip() for line in (run or "").split("\n"))
    return any(COMMAND[kind].search(_without_quoted_text(line)) for line in lines if line and not line.startswith("#"))


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _meaningful(line: str) -> bool:
    return bool(line.strip()) and not line.lstrip().startswith("#")


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def _step_keys(lines: list[str], key_indent: int) -> dict[str, str]:
    """The `name`, `uses` and `run` of one step (its first line's `- ` already turned into spaces)."""
    keys: dict[str, str] = {}
    index = 0
    while index < len(lines):
        match = re.match(rf"^ {{{key_indent}}}([A-Za-z_-]+):[ \t]*(.*)$", lines[index])
        index += 1
        if not match:
            continue
        key, rest = match.group(1), match.group(2)
        if re.fullmatch(r"[|>][+-]?\d?\s*(?:#.*)?", rest):
            block = []
            while index < len(lines) and (not lines[index].strip() or _indent(lines[index]) > key_indent):
                block.append(lines[index])
                index += 1
            keys[key] = textwrap.dedent("\n".join(block)).strip("\n")
        elif key == "uses":
            keys[key] = rest.split()[0] if rest.split() else ""
        else:
            keys[key] = _unquote(re.sub(r"\s+#.*$", "", rest) if key != "run" else rest)
    return keys


def read_jobs(text: str) -> dict[str, dict]:
    """Every job of a workflow: {name: {"container": bool, "steps": [{"name", "uses", "run"}, ...]}}."""
    lines = text.replace("\r\n", "\n").split("\n")
    starts = [i for i, line in enumerate(lines) if re.match(r"^jobs:\s*(?:#.*)?$", line)]
    assert len(starts) == 1, "expected one top-level jobs: key"
    body = []
    for line in lines[starts[0] + 1 :]:
        if _meaningful(line) and _indent(line) == 0:
            break
        body.append(line)
    job_indent = min(_indent(line) for line in body if _meaningful(line))
    heads = [i for i, line in enumerate(body) if _meaningful(line) and _indent(line) == job_indent]
    jobs: dict[str, dict] = {}
    for number, head in enumerate(heads):
        match = re.match(rf"^ {{{job_indent}}}([A-Za-z0-9_-]+):\s*(?:#.*)?$", body[head])
        assert match, f"cannot read the job line {body[head]!r}"
        job = body[head + 1 : heads[number + 1] if number + 1 < len(heads) else len(body)]
        key_indent = min((_indent(line) for line in job if _meaningful(line)), default=job_indent + 2)
        container = any(re.match(rf"^ {{{key_indent}}}container:", line) for line in job)
        steps_at = [i for i, line in enumerate(job) if re.match(rf"^ {{{key_indent}}}steps:\s*(?:#.*)?$", line)]
        steps: list[dict] = []
        if steps_at:
            rest = job[steps_at[0] + 1 :]
            dashes = [line for line in rest if _meaningful(line)]
            assert dashes and dashes[0].lstrip().startswith("- "), f"job {match.group(1)}: steps: is not a list"
            dash = _indent(dashes[0])
            current: list[str] | None = None
            for line in rest:
                if _meaningful(line) and (
                    _indent(line) < dash or (_indent(line) == dash and not line.lstrip().startswith("- "))
                ):
                    break
                if _meaningful(line) and _indent(line) == dash:
                    if current is not None:
                        steps.append(_step_keys(current, dash + 2))
                    current = [" " * (dash + 2) + line[dash + 2 :]]
                elif current is not None:
                    current.append(line)
            if current is not None:
                steps.append(_step_keys(current, dash + 2))
        jobs[match.group(1)] = {"container": container, "steps": steps}
    return jobs


def unset_steps(file: str, jobs: dict[str, dict]) -> list[str]:
    """The steps of one workflow that run a runtime before (or without) setting it up: "file > job > step > kind"."""
    found = []
    for name, job in jobs.items():
        if job["container"]:
            continue
        for kind in COMMAND:
            setups = [i for i, step in enumerate(job["steps"]) if SETUP[kind].search(step.get("uses", ""))]
            setup = setups[0] if setups else None
            for i, step in enumerate(job["steps"]):
                if (setup is None or setup > i) and runs_runtime(step.get("run"), kind):
                    found.append(f"{file} > {name} > {step.get('name') or f'step {i + 1}'} > {kind}")
    return found


@pytest.mark.parametrize(
    "line",
    [
        'token="$(node scripts/github-app-token.mjs)"',
        "npm ci --no-audit",
        "FOO=1 node x",
        "env FOO=1 node x",
        "sudo node x",
        "xargs node x",
        "diff a <(node x)",
        "(node x)",
        "if node x; then",
        "! node x",
        "time node x",
        "exec node x",
        "cd y && npm ci",
    ],
)
def test_node_in_command_position_is_found(line):
    assert runs_runtime(line, "node")


@pytest.mark.parametrize(
    "line",
    [
        "cat x | python3 -I check.py",
        "python3.15 -I x.py",
        'compare_out="$(python3 -I scripts/follow_website_base.py --check)"',
        "python -m pip install uv",
    ],
)
def test_python_in_command_position_is_found(line):
    assert runs_runtime(line, "python")


@pytest.mark.parametrize(
    ("line", "kind"),
    [
        ('echo "run `node scripts/x.mjs` by hand"', "node"),
        ('docker run --rm img python -c "import azure"', "python"),
        ("/opt/az/bin/python3 -Im pip check", "python"),
        ("# node is not run here", "node"),
        ('for node in items["nodes"]:', "node"),
        ('echo "$NODE_VERSION"', "node"),
        ("nodes=3 nodejs-check", "node"),
        ('echo "the stage is wrong; if pip named the file differently, look"', "python"),
        ("uv run python scripts/check.py", "python"),
    ],
)
def test_words_that_are_not_commands_are_not_found(line, kind):
    assert not runs_runtime(line, kind)


def test_a_job_that_sets_the_runtime_up_late_or_never_is_flagged():
    text = textwrap.dedent(
        """\
        name: x
        on: push
        jobs:
          late:
            runs-on: ubuntu-26.04
            steps:
              - name: Early
                run: node a.mjs
              - uses: actions/setup-node@abc # v7
          none:
            runs-on: ubuntu-26.04
            steps:
              - run: python3 b.py
          other-setup:
            runs-on: ubuntu-26.04
            steps:
              - uses: astral-sh/setup-uv@abc
              # A comment between steps does not end the list.
              - name: Run
                run: |
                  set -e
                  python3 c.py
          good:
            runs-on: ubuntu-26.04
            steps:
              - uses: actions/setup-node@abc
              - run: node a.mjs
          boxed:
            runs-on: ubuntu-26.04
            container: node:26
            steps:
              - run: node a.mjs
        """
    )
    assert unset_steps("x.yml", read_jobs(text)) == [
        "x.yml > late > Early > node",
        "x.yml > none > step 1 > python",
        "x.yml > other-setup > Run > python",
    ]


FILES = sorted(p for p in WORKFLOWS.iterdir() if p.suffix in (".yml", ".yaml"))
UNSET = [entry for p in FILES for entry in unset_steps(p.name, read_jobs(p.read_text(encoding="utf-8")))]


def test_the_reader_finds_every_job_and_step():
    """A guard against the line reader missing a job: every `runs-on:` line belongs to a job it read, and every job it
    read that has steps has at least one."""
    for path in FILES:
        text = path.read_text(encoding="utf-8")
        jobs = read_jobs(text)
        runners = len(re.findall(r"(?m)^\s+runs-on:", text))
        assert len(jobs) >= runners, f"{path.name}: read {len(jobs)} jobs, the file has {runners} runs-on lines"
        steps = len(re.findall(r"(?m)^\s+steps:\s*$", text))
        assert sum(1 for job in jobs.values() if job["steps"]) == steps, path.name


def test_every_step_that_runs_node_or_python_comes_after_its_version_is_set_up():
    assert [entry for entry in UNSET if entry not in RUNNER_DEFAULT_ALLOWED] == []


def test_every_allowed_exception_still_exists():
    """So the list cannot hide a step that has since changed."""
    for entry in RUNNER_DEFAULT_ALLOWED:
        assert entry in UNSET, entry
