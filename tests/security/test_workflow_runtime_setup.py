"""Every workflow job that runs Node.js or Python chooses its version (saulpatinojr/HCW-HybridCloudWorks#1707).

A job that runs `node`, `npm`, `npx`, `python3` or `pip` without actions/setup-node or actions/setup-python gets
whatever the runner image ships: on ubuntu-26.04 that was Node.js 24 and Python 3.14 in November 2026, both below the
program's floors (Node.js 26, Python 3.15). Nothing else notices, because a job that names no version has nothing to
read. This is a port of the website's check (scripts/workflow-runtime-setup.test.mjs in HCW-HybridCloudWorks).

A command counts when it is in command position on a line of a `run:` step: at the start, after `$(`, `<(`, a
backtick, `(`, `{`, `|`, `&` or `;`, after leading `NAME=value` assignments, or after a word that runs the next one
(`env`, `sudo`, `xargs`, `exec`, `time`, `!`, `if`, `then`, `do` and the like). It does not count inside a quoted
string (unless a double-quoted string runs a command with `$(`, `<(` or a backtick) or as an argument (`docker run
image python ...`). The set-up step must come before the first such step. Limits, on purpose: a job that runs in a
`container:` uses that image's runtime and is not checked; and a script a step calls (a `.sh` file) is not read.

A set-up step with its own `if:` may be skipped while a later command still runs on the runner's own interpreter
(Copilot on HCW-NetworkEyes_AddOn#100), so it covers a later step only when that step's `if:` is the same condition,
or is one of the terms the set-up's condition joins with a top-level `||` (whenever that step runs, so did the
set-up). Conditions are compared without a surrounding `${{ }}`, with runs of spaces made one, and a term without
one pair of parentheses around the whole of it. A set-up step with no `if:` covers every later step. A job's own
`if:` does not matter here, because it decides whether every step of the job runs, alike.

Each set-up step must also ask for the floor or newer (Copilot on HCW-CloudCrawler_App#81): `python-version` or
`python-version-file`, `node-version` or `node-version-file`, read through `${{ env.X }}` (the step's, job's or
workflow's `env:`), `${{ matrix.X }}` (every entry of the job's matrix list) and the named file. A value this test
cannot work out fails it, naming the step, rather than passing unchecked.

The workflows are read with a small line reader rather than a YAML library, because none is a dependency here. It
relies on the layout every workflow in this repository has (a `jobs:` key at the top level, a `steps:` list, block
`run: |` scripts, `with:` and `env:` written `{ ... }` or as indented `key: value` lines); a file it cannot read that
way fails the test rather than being skipped.
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
    r"(?:^|[$<]\(\s*|`\s*|[({|;&]\s*)"
    r"(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+|(?:env|sudo|xargs|exec|time|nice|command|if|then|else|elif|do|while|until|!)\s+)*"
)
COMMAND = {
    "node": re.compile(START + r"(?:node|npm|npx)(?=\s|$)"),
    "python": re.compile(START + r"(?:python(?:3(?:\.\d+)?)?|pip3?)(?=\s|$)"),
}
SETUP = {"node": re.compile(r"^actions/setup-node@"), "python": re.compile(r"^actions/setup-python@")}

# The lowest versions a set-up step may ask for. The program's floors are kept in scripts/version-floors.json in
# HCW-HybridCloudWorks; change them there first, then here.
PYTHON_FLOOR = (3, 15)
NODE_FLOOR = 26
# The set-up step's inputs that name the version, directly or through a file in the repository.
VERSION_INPUTS = {"python": ("python-version", "python-version-file"), "node": ("node-version", "node-version-file")}


def _without_quoted_text(line: str) -> str:
    """The line with the text of its quoted strings taken out, so words in a message (`echo "...; if pip named..."`)
    do not count. A double-quoted string that runs a command (`"$(node x)"`, or the older "`node x`") is kept. An
    escaped backtick (`\\``, as in Markdown written to the step summary) is a plain character, so it is dropped
    first."""
    line = re.sub(r"'[^']*'", "''", line.replace("\\`", ""))
    return re.sub(r'"(?:[^"\\]|\\.)*"', lambda q: q.group(0) if re.search(r"[$<]\(|`", q.group(0)) else '""', line)


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


def _flow_mapping(text: str) -> dict[str, str]:
    """A one-line `{ key: value, ... }` mapping, split on the commas outside quotes and `${{ }}`."""
    inner = text[text.index("{") + 1 : text.rindex("}")]
    parts, depth, quote, start = [], 0, "", 0
    for index, char in enumerate(inner):
        if quote:
            quote = "" if char == quote else quote
        elif char in "'\"":
            quote = char
        elif char in "{[":
            depth += 1
        elif char in "}]":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(inner[start:index])
            start = index + 1
    parts.append(inner[start:])
    pairs = (part.partition(":") for part in parts if part.strip())
    return {key.strip(): _unquote(value) for key, _, value in pairs}


def _block(lines: list[str], at: int, indent: int) -> list[str]:
    """The lines under the key on line `at` (at `indent` spaces), up to the next line at that indent or less."""
    block = []
    for line in lines[at + 1 :]:
        if _meaningful(line) and _indent(line) <= indent:
            break
        block.append(line)
    return block


def _mapping(lines: list[str], at: int, indent: int) -> dict[str, str]:
    """The mapping under the key on line `at`: a `{ ... }` on the same line, or the `key: value` lines below it."""
    rest = re.sub(r"\s+#.*$", "", lines[at].split(":", 1)[1]).strip()
    if rest.startswith("{"):
        return _flow_mapping(rest)
    block = _block(lines, at, indent)
    inner = min((_indent(line) for line in block if _meaningful(line)), default=indent + 2)
    pairs = (re.match(rf"^ {{{inner}}}([A-Za-z0-9_.-]+):[ \t]*(.*)$", line) for line in block)
    return {m.group(1): _unquote(re.sub(r"\s+#.*$", "", m.group(2))) for m in pairs if m}


def _matrix(job: list[str], key_indent: int) -> dict[str, list[str]]:
    """The lists of a job's `strategy: matrix:`, each written `[a, b]` or as `- a` lines; {} when it has none."""
    strategy = [i for i, line in enumerate(job) if re.match(rf"^ {{{key_indent}}}strategy:\s*(?:#.*)?$", line)]
    if not strategy:
        return {}
    block = _block(job, strategy[0], key_indent)
    at = [i for i, line in enumerate(block) if re.match(r"^\s+matrix:\s*(?:#.*)?$", line)]
    if not at:
        return {}
    matrix_lines = _block(block, at[0], _indent(block[at[0]]))
    inner = min((_indent(line) for line in matrix_lines if _meaningful(line)), default=0)
    found: dict[str, list[str]] = {}
    for index, line in enumerate(matrix_lines):
        match = re.match(rf"^ {{{inner}}}([A-Za-z0-9_-]+):[ \t]*(.*)$", line)
        if not match:
            continue
        rest = re.sub(r"\s+#.*$", "", match.group(2)).strip()
        if rest.startswith("["):
            found[match.group(1)] = [_unquote(v) for v in rest.strip("[]").split(",") if v.strip()]
        else:
            items = _block(matrix_lines, index, inner)
            found[match.group(1)] = [_unquote(i.strip()[2:]) for i in items if i.strip().startswith("- ")]
    return found


def _step_keys(lines: list[str], key_indent: int) -> dict:
    """Every key of one step, among them `name`, `uses`, `run`, `if`, and `with` and `env` as mappings (its first
    line's `- ` already turned into spaces)."""
    keys: dict = {}
    index = 0
    while index < len(lines):
        match = re.match(rf"^ {{{key_indent}}}([A-Za-z_-]+):[ \t]*(.*)$", lines[index])
        index += 1
        if not match:
            continue
        key, rest = match.group(1), match.group(2)
        if key in ("with", "env"):
            keys[key] = _mapping(lines, index - 1, key_indent)
            index += len(_block(lines, index - 1, key_indent))
        elif re.fullmatch(r"[|>][+-]?\d?\s*(?:#.*)?", rest):
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
    """Every job of a workflow: {name: {"container": bool, "env": {...}, "matrix": {...}, "steps": [{"name", "uses",
    "run", "if", "with", "env"}, ...]}}. A job's `env` holds the workflow's `env:` with the job's own on top."""
    lines = text.replace("\r\n", "\n").split("\n")
    top_env = [i for i, line in enumerate(lines) if re.match(r"^env:\s*(?:#.*)?$|^env:\s*\{", line)]
    workflow_env = _mapping(lines, top_env[0], 0) if top_env else {}
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
        env_at = [i for i, line in enumerate(job) if re.match(rf"^ {{{key_indent}}}env:", line)]
        env = {**workflow_env, **(_mapping(job, env_at[0], key_indent) if env_at else {})}
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
        jobs[match.group(1)] = {"container": container, "env": env, "matrix": _matrix(job, key_indent), "steps": steps}
    return jobs


def _normalized(expression: str) -> str:
    """An `if:` expression without a surrounding `${{ }}` and with runs of spaces made one."""
    text = expression.strip()
    wrapped = re.fullmatch(r"\$\{\{(.*)\}\}", text, re.DOTALL)
    return " ".join((wrapped.group(1) if wrapped else text).split())


def _top_level_or_terms(expression: str) -> list[str]:
    """The terms an expression joins with `||` outside parentheses and quotes, each without one pair of parentheses
    around the whole of it; a one-item list when there is no such `||`."""
    terms, depth, quote, start, index = [], 0, "", 0, 0
    while index < len(expression):
        char = expression[index]
        if quote:
            quote = "" if char == quote else quote
        elif char in "'\"":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif depth == 0 and expression.startswith("||", index):
            terms.append(expression[start:index])
            start = index + 2
            index += 1
        index += 1
    terms.append(expression[start:])
    return [_without_outer_parentheses(term.strip()) for term in terms]


def _without_outer_parentheses(term: str) -> str:
    """The term without one pair of parentheses, when that pair encloses the whole of it."""
    if not (term.startswith("(") and term.endswith(")")):
        return term
    depth = 0
    for index, char in enumerate(term):
        depth += {"(": 1, ")": -1}.get(char, 0)
        if depth == 0 and index < len(term) - 1:
            return term
    return term[1:-1].strip()


def condition(step: dict) -> str:
    """A step's `if:` as one comparable expression ("" when it has none)."""
    return _normalized(str(step.get("if") or ""))


def covers(setup: dict, step: dict) -> bool:
    """True when a set-up step runs whenever the later step does: it has no `if:`, the same `if:`, or an `if:` whose
    top-level `||` terms include the later step's."""
    wanted, given = condition(step), condition(setup)
    return given in ("", wanted) or wanted in _top_level_or_terms(given)


def unset_steps(file: str, jobs: dict[str, dict]) -> list[str]:
    """The steps of one workflow that run a runtime before (or without) setting it up: "file > job > step > kind". A
    step needs an earlier set-up step that covers it (see `covers`)."""
    found = []
    for name, job in jobs.items():
        if job["container"]:
            continue
        for kind in COMMAND:
            for i, step in enumerate(job["steps"]):
                if not runs_runtime(step.get("run"), kind):
                    continue
                covered = any(
                    SETUP[kind].search(earlier.get("uses", "")) and covers(earlier, step)
                    for earlier in job["steps"][:i]
                )
                if not covered:
                    found.append(f"{file} > {name} > {step.get('name') or f'step {i + 1}'} > {kind}")
    return found


def _resolved(value: str, step: dict, job: dict, depth: int = 0) -> list[str] | None:
    """The plain values an input stands for: itself, or what `${{ env.X }}` (the step's, job's or workflow's `env:`) or
    `${{ matrix.X }}` (every entry of the job's matrix list) holds. None when it cannot be worked out here."""
    found = re.fullmatch(r"\$\{\{\s*(env|matrix)\.([A-Za-z0-9_-]+)\s*\}\}", value.strip())
    if not found:
        return None if "${{" in value else [value.strip()]
    source, name = found.groups()
    if source == "env":
        env = {**job.get("env", {}), **step.get("env", {})}
        return _resolved(env[name], step, job, depth + 1) if name in env and depth < 5 else None
    return job.get("matrix", {}).get(name) or None


def requested_versions(step: dict, job: dict, root: Path) -> list[str] | None:
    """The versions a set-up step asks for, read through `env`, `matrix` and a version file; None when unreadable."""
    direct, from_file = VERSION_INPUTS["python" if SETUP["python"].search(step.get("uses", "")) else "node"]
    given = step.get("with") or {}
    if direct in given:
        return _resolved(str(given[direct]), step, job)
    if from_file not in given:
        return None
    paths = _resolved(str(given[from_file]), step, job) or []
    if len(paths) != 1 or not (root / paths[0]).is_file():
        return None
    lines = (line.strip() for line in (root / paths[0]).read_text(encoding="utf-8").splitlines())
    return [line for line in lines if line and not line.startswith("#")] or None


def _below_floor(version: str, kind: str) -> bool | None:
    """True when the version is under the floor, False when at or above it, None when it is not a version number."""
    if kind == "python":
        found = re.match(r"(\d+)\.(\d+)(?!\d)", version)
        return None if not found else (int(found.group(1)), int(found.group(2))) < PYTHON_FLOOR
    found = re.match(r"v?(\d+)(?!\d)", version)
    return None if not found else int(found.group(1)) < NODE_FLOOR


def floor_problems(file: str, jobs: dict[str, dict], root: Path = ROOT) -> list[str]:
    """Every set-up step that asks for a version below the floor, or one this test cannot read, with the reason."""
    problems = []
    for name, job in jobs.items():
        for i, step in enumerate(job["steps"]):
            for kind in COMMAND:
                if not SETUP[kind].search(step.get("uses", "")):
                    continue
                label = f"{file} > {name} > {step.get('name') or f'step {i + 1}'} > {kind}"
                versions = requested_versions(step, job, root)
                if not versions:
                    problems.append(f"{label}: cannot work out the version it asks for")
                for version in versions or []:
                    below = _below_floor(version, kind)
                    if below is None:
                        problems.append(f"{label}: {version!r} is not a version number this test can compare")
                    elif below:
                        problems.append(f"{label}: asks for {version}, below the floor")
    return problems


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
        'echo "`node --version`"',
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
        "version=`python3 scripts/check.py`",
        'echo "`python3 --version`"',
    ],
)
def test_python_in_command_position_is_found(line):
    assert runs_runtime(line, "python")


@pytest.mark.parametrize(
    ("line", "kind"),
    [
        ('echo "run \\`node scripts/x.mjs\\` by hand"', "node"),
        ('docker run --rm img python -c "import azure"', "python"),
        ("/opt/az/bin/python3 -Im pip check", "python"),
        ("# node is not run here", "node"),
        ('for node in items["nodes"]:', "node"),
        ('echo "$NODE_VERSION"', "node"),
        ("nodes=3 nodejs-check", "node"),
        ('echo "the stage is wrong; if pip named the file differently, look"', "python"),
        ("uv run python scripts/check.py", "python"),
        ("echo 'literal `python3` text'", "python"),
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


def test_a_set_up_step_with_its_own_condition_covers_only_steps_it_always_runs_before():
    text = textwrap.dedent(
        """\
        name: x
        on: push
        jobs:
          skipped:
            runs-on: ubuntu-26.04
            steps:
              - uses: actions/setup-python@abc
                if: false
              - name: Run
                run: python3 a.py
          same-condition:
            runs-on: ubuntu-26.04
            steps:
              - uses: actions/setup-python@abc
                if: ${{ !cancelled() }}
              - name: Run
                if: "!cancelled()"
                run: python3 a.py
          unconditional-setup:
            runs-on: ubuntu-26.04
            steps:
              - uses: actions/setup-python@abc
              - name: Run
                if: failure()
                run: python3 a.py
          other-condition:
            runs-on: ubuntu-26.04
            steps:
              - uses: actions/setup-python@abc
                if: github.event_name == 'push'
              - name: Run
                if: failure()
                run: python3 a.py
          or-term:
            runs-on: ubuntu-26.04
            steps:
              - uses: actions/setup-node@abc
                if: matrix.relevant == 'true' || (matrix.name == 'scripts (operations)')
              - name: Run
                if: matrix.name == 'scripts (operations)'
                run: node a.mjs
          and-term:
            runs-on: ubuntu-26.04
            steps:
              - uses: actions/setup-node@abc
                if: matrix.relevant == 'true' && matrix.name == 'scripts'
              - name: Run
                if: matrix.name == 'scripts'
                run: node a.mjs
          job-condition:
            if: github.event_name == 'push'
            runs-on: ubuntu-26.04
            steps:
              - uses: actions/setup-node@abc
              - run: node a.mjs
        """
    )
    assert unset_steps("x.yml", read_jobs(text)) == [
        "x.yml > skipped > Run > python",
        "x.yml > other-condition > Run > python",
        "x.yml > and-term > Run > node",
    ]


@pytest.mark.parametrize(
    ("setup", "step", "covered"),
    [
        ("${{  a &&   b }}", "a && b", True),
        ("a || b", "b", True),
        ("(a) || (b && c)", "b && c", True),
        ("x == 'p || q' || r", "x == 'p", False),
        ("(a || b) && c", "a", False),
        ("a || b", "a || c", False),
        ("", "anything", True),
    ],
)
def test_covers_compares_normalised_conditions_and_top_level_or_terms(setup, step, covered):
    assert covers({"if": setup}, {"if": step}) is covered


def test_a_set_up_step_must_ask_for_the_floor_or_newer(tmp_path):
    (tmp_path / ".python-version").write_text("# the line uv and setup-python read\n3.15\n", encoding="utf-8")
    (tmp_path / ".old-version").write_text("3.14\n", encoding="utf-8")
    text = textwrap.dedent(
        """\
        name: x
        on: push
        env:
          PYTHON_VERSION: "3.15"
          OLD: "3.14"
        jobs:
          old:
            runs-on: ubuntu-26.04
            steps:
              - uses: actions/setup-python@abc
                with: { python-version: "3.14" }
          new:
            runs-on: ubuntu-26.04
            steps:
              - uses: actions/setup-python@abc # v6
                with:
                  python-version: "3.15"
              - uses: actions/setup-python@abc
                with: { python-version-file: .python-version }
              - uses: actions/setup-python@abc
                with: { python-version: "${{ env.PYTHON_VERSION }}" }
              - uses: actions/setup-node@abc
                with: { node-version: 26, package-manager-cache: false }
          old-node:
            runs-on: ubuntu-26.04
            steps:
              - name: Node
                uses: actions/setup-node@abc
                with: { node-version: "24" }
          through-env:
            runs-on: ubuntu-26.04
            env:
              PYTHON_VERSION: ${{ env.OLD }}
            steps:
              - uses: actions/setup-python@abc
                with: { python-version: "${{ env.PYTHON_VERSION }}" }
              - uses: actions/setup-python@abc
                with: { python-version-file: .old-version }
          matrix:
            runs-on: ubuntu-26.04
            strategy:
              matrix:
                python-version: ["3.15", "3.14"]
            steps:
              - uses: actions/setup-python@abc
                with: { python-version: "${{ matrix.python-version }}" }
          unreadable:
            runs-on: ubuntu-26.04
            steps:
              - uses: actions/setup-python@abc
              - uses: actions/setup-node@abc
                with: { node-version: "${{ inputs.node }}" }
              - uses: actions/setup-node@abc
                with: { node-version: lts/* }
        """
    )
    assert floor_problems("x.yml", read_jobs(text), tmp_path) == [
        "x.yml > old > step 1 > python: asks for 3.14, below the floor",
        "x.yml > old-node > Node > node: asks for 24, below the floor",
        "x.yml > through-env > step 1 > python: asks for 3.14, below the floor",
        "x.yml > through-env > step 2 > python: asks for 3.14, below the floor",
        "x.yml > matrix > step 1 > python: asks for 3.14, below the floor",
        "x.yml > unreadable > step 1 > python: cannot work out the version it asks for",
        "x.yml > unreadable > step 2 > node: cannot work out the version it asks for",
        "x.yml > unreadable > step 3 > node: 'lts/*' is not a version number this test can compare",
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


def test_every_set_up_step_asks_for_the_floor_or_newer():
    problems = [problem for p in FILES for problem in floor_problems(p.name, read_jobs(p.read_text(encoding="utf-8")))]
    assert problems == []


def test_every_step_that_runs_node_or_python_comes_after_its_version_is_set_up():
    assert [entry for entry in UNSET if entry not in RUNNER_DEFAULT_ALLOWED] == []


def test_every_allowed_exception_still_exists():
    """So the list cannot hide a step that has since changed, and every entry says why."""
    for entry, reason in RUNNER_DEFAULT_ALLOWED.items():
        assert isinstance(reason, str) and reason.strip(), f"{entry}: an exception needs a reason"
        assert entry in UNSET, entry
