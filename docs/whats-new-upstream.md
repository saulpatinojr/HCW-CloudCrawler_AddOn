# What's new upstream

The memory file for this repository about its upstream, `saulpatinojr/HCW-CloudCrawler_App` (the App edition). Newest
entries first. Written for a reader, human or Claude session, who has not seen earlier conversations.

## How to use this file

Read it before you change behaviour here, adopt a new engine release, or answer a question about what the App has
done. When the App changes something that reaches this repository, add an entry at the top of "What changed" in the
same change set (the App's `CLAUDE.md` asks for this too), and refresh the table below.

## Current upstream state

Written on 2026-10-24 against the App's `main` at commit `856b54b` (merge of pull request
[24](https://github.com/saulpatinojr/HCW-CloudCrawler_App/pull/24), documents only; the commit before it, `697cdc4`, is the
last one that changed anything but documents).

| Question | Answer | How it was checked |
| --- | --- | --- |
| Has the App published a release? | **No.** There is no tag and no GitHub Release. `v0.1.0` was prepared on 2026-10-21 (changelog dated, workflows ready) but never tagged. | GitHub releases and tags lists for the App, both empty, 2026-10-24; App ticket [7](https://github.com/saulpatinojr/HCW-CloudCrawler_App/issues/7) |
| So what does `core-update.yml` do today? | **Nothing, by design.** It looks for a `# CORE_REF v<version>` line in `pyproject.toml`, finds none, and stops. Even after a release exists, it stays inert until that line is added by hand (see "First adoption"). | `.github/workflows/core-update.yml` in this repository |
| Engine version in the App | `cloud-crawler-core` 0.1.0 (`packages/cloud-crawler-core/pyproject.toml`); the App edition is also 0.1.0 | Read from the App |
| What this repository pins | **No engine yet.** `pyproject.toml` has no `cloud-crawler-core` line. A copy of the engine's redaction module lives in `src/cloud_crawler_lab/security/redaction.py` until adoption. | `pyproject.toml`, `security/redaction.py` header |
| Has the engine's public surface changed since the release was prepared (2026-10-21)? | **No.** Nothing under `packages/`, `src/`, `tests/contract/`, `samples/` or `scripts/` changed after commit `4ba5add`. Only tests, workflows and documents did. | `git diff --stat 4ba5add 697cdc4 -- packages src tests/contract samples scripts` printed nothing |
| Compatible with this repository's pins? | Yes. Both require Python `>=3.14.6,<3.15`. The engine requires only `pydantic>=2.14,<3`; this repository pins `pydantic==2.14.1`. Both use `fastapi==0.143.3`. | App `VALIDATION.md` (wheel row) and both `pyproject.toml` files |
| Azure MCP Server | Pinned to 3.0.0 in the App (ADR 0001). **This repository never calls it.** | App ADR 0001 and 0003 |

## What changed

### 2026-10-24: documents and rules (App pull request 24, merged)

- **Is there a user interface in the App?** No, by design. The App is an API plus an MCP server. The screens are in the
  website (sign-in, tenant and subscription pickers, chat, evidence and drift views, approvals) and in this
  repository's pane (`web/`). The App marks a sign-in and chat of its own as optional, for an "enterprise package",
  and has built neither. Source: the website proposal *Azure Architecture MCP Appliance on Azure MCP Server 3.0*,
  sections 7, 9 and 17.
- The App README now says so, documents its branch and tag protection, and its release steps match its changelog.
- Reaches this repository? **No code.** Action: none.

### 2026-10-24: the GUID-scan test (App pull requests 22 and 23, merged)

- The App's test that looks for real-looking identifiers read compiled Python caches, which embed the checkout path;
  a checkout whose path contained a GUID failed with dozens of false hits. It now skips caches (and a second test
  proves a `.pyc` or `.pyo` outside `__pycache__` is also skipped), and a real-looking GUID in source is still caught.
- Reaches this repository? **No, and no change is needed.** `tests/security/test_no_secrets.py` here lists files with
  `git ls-files --cached --others --exclude-standard`, and `.gitignore` ignores `__pycache__/`, so bytecode is never
  read. If you ever copy the App's scan, copy the fixed one.

### 2026-10-24: release pipeline hardened (App pull request 21, merged)

- `publish-core.yml` no longer overwrites published files: attaching an asset whose name already exists **fails**
  (delete the asset by hand to retry). It now also writes a CycloneDX software bill of materials of the engine's locked
  runtime dependencies and attests it, and attests the wheel's build provenance (`actions/attest` and
  `actions/attest-build-provenance`, both v4.2.2, pinned by commit). `codeql.yml` and `dependency-review.yml` use the
  same runner label as every other workflow.
- Reaches this repository? **Yes, at the first release.** A release will carry three files, not two:
  `cloud_crawler_core-<version>-py3-none-any.whl`, `cloud_crawler_core-<version>.tar.gz` and
  `cloud-crawler-core.cdx.json`. `core-update.yml` here reads only the latest release's tag name and builds the wheel
  URL from it, so the extra file does not matter.
- **Not yet proven:** the release path has never run. Treat the first release as the test (App ticket
  [16](https://github.com/saulpatinojr/HCW-CloudCrawler_App/issues/16)).

### 2026-10-24: repository rules switched on (App pull request 19, merged)

- The App has two rulesets: `main` takes changes only through a pull request with the checks `lint`, `test`,
  `contract`, `pip-audit`, `secret-scan` and `image` passing, and `v*` tags **cannot be moved or deleted** once pushed.
  They were applied by the App's manual `repository-admin` workflow. It needs no approving review (count 0).
- Reaches this repository? **Yes, indirectly.** If a wrong tag is pushed, the fix is a new version number, never
  re-tagging, so `core-update.yml` here should be ready to move from one tag to a later one. It compares tag strings
  and handles that.

### 2026-10-24: working rules (App `CLAUDE.md`, pull requests 6, 18 and 20)

- Owner communication rules (plain language, numbered steps, answerable questions, exact values with descriptions for
  form fields, secrets never in chat, pull requests or documents) and a rule to keep this file current.
- Reaches this repository? **Process only.** This repository's `CLAUDE.md` now carries the same communication rules.

### 2026-10-21: first implementation slice and release preparation (App pull requests 2 and 5, merged)

- The engine `cloud-crawler-core` 0.1.0: evidence, provenance, collection-run, decision, claim, drift-finding,
  contradiction and review models; canonical hashing; redaction; the Azure Resource Graph export normaliser; ten
  detectors (`zone-redundancy`, `public-access-disabled`, `private-endpoint-present`, `managed-identity`,
  `tag-required`, `sku-allowed`, `region-allowed` and the observation detectors `advisor-findings`,
  `retirement-exposure`, `policy-assignment-present`); the drift engine; the in-memory ledger; the report bundle.
- **What the wheel does not contain:** the MCP server, the HTTP API, the Azure MCP host and every tool that calls
  Azure. They live in the App's `src/cloud_crawler_appliance` and never enter the engine (App ADR 0002, item 4), so
  this repository writes its own MCP server and API on top of the engine.
- The tool catalogue this repository's MCP server should match (App README): `adr_create`, `adr_get`, `adr_list`,
  `evidence_ingest`, `evidence_list`, `evidence_get`, `drift_evaluate`, `drift_list`, `contradiction_list`,
  `review_list`, `review_get` and `review_propose` for the model; the human-only `adr_accept` and `review_decide`.
  Every tool declares `meta.caller` and `meta.callsAzure`. The App's `collection_run_azure` (the only tool with
  `callsAzure: true`) is **App only** and must never appear here; this repository's security suite fails if any
  tool says `true`.
- Reaches this repository? **Yes, at adoption.** Action: see "First adoption".

## First adoption (when the App's `v0.1.0` exists)

`core-update.yml` cannot do the first step; it needs an existing `CORE_REF` line. Do it by hand, once:

1. Confirm the release exists and lists the three files above. If it does not, stop; nothing can be adopted.
2. In `pyproject.toml`, add to `dependencies`, on one line (the workflow's `sed` expects exactly this shape):
   `"cloud-crawler-core @ https://github.com/saulpatinojr/HCW-CloudCrawler_App/releases/download/v0.1.0/cloud_crawler_core-0.1.0-py3-none-any.whl",  # CORE_REF v0.1.0`
3. Run `uv lock`. It records the wheel's sha256, and the image build's `pip install --require-hashes` then verifies it.
4. Delete `src/cloud_crawler_lab/security/redaction.py` and point the two imports (in `security/logging.py` and
   `__main__.py`) and the tests that import it at the engine's `cloud_crawler_core.redaction`, as that file's header
   says. The two modules must be identical until then.
5. Add the engine's capabilities to `edition.py` (`CAPABILITIES`, only ever added, never renamed), then build the
   upload route, the MCP server and the trusted-caller session API on the engine. The pane's text "uploads open with
   the App's first release" and `samples/README.md` change when this lands.
6. Run `uv sync --all-packages`, `uv run ruff check . && uv run ruff format --check .` and
   `uv run pytest -q --cov=src --cov-fail-under=85`. The edition boundary tests
   (`tests/security/test_edition_boundary.py`) must still pass: the engine has no cloud SDK and no HTTP client (the
   App's `scripts/verify-core-wheel.py` checks this before it attaches the wheel).
7. Update `CHANGELOG.md`, `VALIDATION.md` and the "Current upstream state" table here.

## Upstream decisions you can cite (not copied here)

The App has published three decisions: [0001](https://github.com/saulpatinojr/HCW-CloudCrawler_App/blob/main/docs/adr/0001-pin-azure-mcp-server-3-0-0.md)
(Azure MCP Server pinned to 3.0.0), [0002](https://github.com/saulpatinojr/HCW-CloudCrawler_App/blob/main/docs/adr/0002-engine-moves-downstream-unchanged.md)
(the engine moves downstream unchanged) and [0003](https://github.com/saulpatinojr/HCW-CloudCrawler_App/blob/main/docs/adr/0003-the-addon-never-calls-azure.md)
(only the App and the website call Azure MCP). This repository's own decisions are in `docs/adr/`.

## Open upstream decisions that affect this repository

| App ticket | What it is | Why it matters here |
| --- | --- | --- |
| [7](https://github.com/saulpatinojr/HCW-CloudCrawler_App/issues/7): tag and release `v0.1.0` | Owner step; publishes artifacts | **Blocks everything above.** Until it happens there is no engine to adopt. |
| [8](https://github.com/saulpatinojr/HCW-CloudCrawler_App/issues/8): no sign-in on the App's `/api` and `/mcp` | The "human only" gate is a non-empty `actorId` today; an authentication model needs an owner decision | The caller classes and identity model it picks may change the tool contract this repository must match. Here, identity stays the website's job (asserted claims only); watch for a contract change. |
| [9](https://github.com/saulpatinojr/HCW-CloudCrawler_App/issues/9): protect `main` and tags | Partly done: pull request plus six checks, `v*` tags locked, but no approving review is required and `CODEOWNERS` still has placeholders | None directly. |
| [13](https://github.com/saulpatinojr/HCW-CloudCrawler_App/issues/13): GUID-scan false alarm | Fixed for bytecode; "scan only tracked files" is not done in the App | This repository already scans only files git lists. |
| [16](https://github.com/saulpatinojr/HCW-CloudCrawler_App/issues/16): release hygiene | Done in the workflows; unproven until the first tag | The first adoption is the first real test of the release assets. |
