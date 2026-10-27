# What's new upstream

The memory file for this repository about its upstream, `saulpatinojr/HCW-CloudCrawler_App` (the App edition). Newest
entries first. Written for a reader, human or Claude session, who has not seen earlier conversations.

## How to use this file

Read it before you change behaviour here, adopt a new engine release, or answer a question about what the App has
done. When the App changes something that reaches this repository, add an entry at the top of "What changed" in the
same change set (the App's `CLAUDE.md` asks for this too), and refresh the table below.

## Current upstream state

Written on 2026-10-26 against the App's release [v0.1.0](https://github.com/saulpatinojr/HCW-CloudCrawler_App/releases/tag/v0.1.0)
(published 2026-10-26 04:00 UTC from commit `8142b69`). Before that, on 2026-10-24, the App's `main` was at commit `9bad3d1`
(merge of pull request [34](https://github.com/saulpatinojr/HCW-CloudCrawler_App/pull/34), Microsoft Entra sign-in in the App
host); nothing under `packages/` had changed since commit `4ba5add`.

| Question | Answer | How it was checked |
| --- | --- | --- |
| Has the App published a release? | **Yes: `v0.1.0`** (2026-10-26). Three files: `cloud_crawler_core-0.1.0-py3-none-any.whl`, `cloud_crawler_core-0.1.0.tar.gz` and `cloud-crawler-core.cdx.json` (the software bill of materials). | `gh release view v0.1.0 --repo saulpatinojr/HCW-CloudCrawler_App`; App ticket [7](https://github.com/saulpatinojr/HCW-CloudCrawler_App/issues/7) |
| What does `core-update.yml` do today? | It reads the `# CORE_REF v0.1.0` line now in `pyproject.toml` and compares it with the App's latest release. At `v0.1.0` it reports "already at v0.1.0" and stops; when the App tags a newer release it opens the bump pull request, moving the pin and the version line of the engine's static metadata (marker `# CORE_METADATA`, see "First adoption" item 6) together. | `.github/workflows/core-update.yml`; the first adoption added the line by hand (see "First adoption", done) |
| Engine version in the App | `cloud-crawler-core` 0.1.0; the App edition is also 0.1.0 | Read from the release |
| What this repository pins | **`cloud-crawler-core` 0.1.0**, by release-asset URL on one line of `pyproject.toml`, with the wheel's sha256 `25a7abfcec50b0f85cb427145a1fd7fb57898bd09cfc3483edad8a042e5e7be3` recorded in `uv.lock`. The sha256 was computed from a fresh download of the release asset and equals GitHub's own digest for it; the build provenance verifies with `gh attestation verify` (signer: the App's `publish-core.yml` at `refs/tags/v0.1.0`, commit `8142b69`). | `gh release download`, `sha256sum`, `gh attestation verify ... --repo saulpatinojr/HCW-CloudCrawler_App` on 2026-10-26 |
| Does the engine's log-word list match the lab's? | **No, and it is not copied any more.** The old copy of the engine's redaction module had drifted: ten words that only the lab logs (`session_opened`, `session_closed`, the five `turnstile_*` outcomes, `unsupported_media_type`, `arg-json`, `arg-csv`) are not in the engine's list. `security/redaction.py` is now a thin module: the engine's `scrub`, `VisitorDataError` and guard, plus those ten words. | `tests/security/test_engine_adoption.py` |
| Compatible with this repository's pins? | Yes. Both require Python `>=3.14.6,<3.15`. The engine requires only `pydantic>=2.14,<3`; this repository pins `pydantic==2.14.1`. The engine imports no cloud SDK and nothing that opens a connection (checked here by walking its installed source). | `uv sync`, the tests above, and the full suite on 2026-10-26 |
| Azure MCP Server | Pinned to 3.0.0 in the App (ADR 0001). **This repository never calls it.** | App ADR 0001 and 0003 |

## What changed

### 2026-10-26: the App's first release, `v0.1.0`, adopted here

- The App tagged `v0.1.0`: the engine `cloud-crawler-core` 0.1.0 (wheel, sdist, CycloneDX bill of materials, build
  provenance), the App edition 0.1.0 and its optional Microsoft Entra sign-in (off by default, ADR 0004). The engine
  itself is the same code that was prepared on 2026-10-21.
- Reaches this repository? **Yes, adopted.** `pyproject.toml` pins the wheel by URL, `uv.lock` records its sha256, and the
  redaction module is now a thin layer over the engine's. See "First adoption" for what was done and what was not.

### 2026-10-24: Microsoft Entra sign-in in the App host (App pull request 34, merged; ADR 0004, App ticket 8)

- The App's server can now require a Microsoft Entra access token on `/api` and `/mcp` (everything except `GET /api/health`).
  It is **off by default** (`CC_AUTH_MODE=off`), so nothing changes until the App is configured. The tools meant for a
  person (`adr_accept`, `review_decide`, `collection_run_azure`) take the actor from the token instead of from what the
  caller types, and their `actorId` argument became **optional** in the App's tool schemas.
- The engine (`cloud-crawler-core`) is unchanged: no new dependency, model, detector or evidence kind, so the next
  `core-update` brings nothing from this.
- Reaches this repository? **No code, no wheel, no action.** This repository keeps its own rules: no Azure credential, no
  validation of Entra tokens, human verification on uploads, `callsAzure: false` on every tool. If this repository's
  security suite ever compares the App's tool list with its own, `actorId` moving from required to optional is the only
  schema difference.

### 2026-10-24: App tests and coverage (App pull request 33, merged)

- The App's secret-scan test now asks git which files exist (`git ls-files --cached --others --exclude-standard`) instead
  of walking the folder, and the App's coverage figure now counts source files only (the CI gate went from 85 to 96
  percent). A new test runs the App's `__main__` and the Azure MCP host with a stand-in client.
- Reaches this repository? **No.** `tests/security/test_no_secrets.py` here already lists files with git, and this
  repository's own coverage gate is separate. Action: none.

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

## First adoption (done 2026-10-26, engine `v0.1.0`)

`core-update.yml` could not do the first step; it needs an existing `CORE_REF` line. It was done by hand, once. What was
done, and where it differed from the plan this file used to carry:

1. Confirmed the release exists and lists the three files. Downloaded them into a scratch folder, hashed them, and
   checked the wheel's build provenance with `gh attestation verify` (the bill of materials is attested against the wheel).
2. In `pyproject.toml`, added to `dependencies`, on one line (the workflow's `sed` expects exactly this shape):
   `"cloud-crawler-core @ https://github.com/saulpatinojr/HCW-CloudCrawler_App/releases/download/v0.1.0/cloud_crawler_core-0.1.0-py3-none-any.whl",  # CORE_REF v0.1.0`
   **One more line was needed that the plan did not know about:** `[tool.hatch.metadata] allow-direct-references = true`.
   Without it the build tool (hatchling) refuses a dependency that is a URL, and `uv sync` fails. It only matters for
   building this project's own wheel, which is never published (the image copies the source tree).
3. Ran `uv lock` (CI's uv, 0.11.32). It recorded the wheel's sha256 in `uv.lock`; the image build's
   `pip install --require-hashes` verifies it, and a local image build proved that.
4. **Did not delete `security/redaction.py`.** The plan said to delete it and import the engine's module, on the belief
   that the two files were identical. They were not (see the table above), and using the engine's guard alone would
   have made the lab refuse to log `turnstile_disabled` at startup. The file now re-exports the engine's `scrub`,
   `VisitorDataError` and guard, and adds the ten lab-only words. If the App ever adds those words to the engine, remove
   them from `LAB_ONLY_WORDS` (a test fails while a word is in both lists).
5. **Not done at adoption, on purpose: the upload route, the MCP server and the trusted-caller session API.** `edition.py`'s
   `CAPABILITIES` stayed `("health", "pane")` because it must only list what exists. This is feature work, not adoption,
   and it decides whether the website can honestly show the tool as available.
6. **Missed at adoption, added 2026-10-27 ([issue 33](https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/issues/33)): the
   engine's metadata.** Pinning the wheel by address made Dependabot's Python job fail for every package, because uv asked
   that address for the wheel's metadata each time it rebuilt the lock. `pyproject.toml` now carries a
   `[[tool.uv.dependency-metadata]]` entry for the engine (its version line ends in `# CORE_METADATA`), `core-update.yml`
   moves that version with the pin, and a test compares the entry's other fields with the installed wheel. So an engine
   release that changes the engine's dependencies or Python range turns the bump pull request red until the entry is
   updated by hand. Runbook: "Keeping Dependabot's Python updates working" in `docs/operations/runbook.md`.
   **Update, 2026-10-26: the upload route is built** ([issue 16](https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/issues/16),
   [ADR 0004](adr/0004-the-upload-route.md), [`docs/api.md`](api.md)); it is the content of release `0.2.0`, and
   `CAPABILITIES` now lists it. It calls the engine's `ingest` and `evaluate_decision` and `bundle` as published, and builds
   the decision record the way the App's `adr_create` tool does (the engine does not contain that step: it lives in the
   App's `mcp_server.py`, so the lab keeps its own copy with limits, and the App's golden verdicts hold it to the same
   answers). Still not done: the MCP server surface and the trusted-caller session API (later releases).
6. Ran `uv sync --all-packages`, `uv run ruff check . && uv run ruff format --check .` and
   `uv run pytest -q --cov=src --cov-fail-under=85` (70 passed, 95 percent), and built the image locally.
7. Updated `CHANGELOG.md`, `VALIDATION.md` and the "Current upstream state" table here.

## Upstream decisions you can cite (not copied here)

The App has published three decisions: [0001](https://github.com/saulpatinojr/HCW-CloudCrawler_App/blob/main/docs/adr/0001-pin-azure-mcp-server-3-0-0.md)
(Azure MCP Server pinned to 3.0.0), [0002](https://github.com/saulpatinojr/HCW-CloudCrawler_App/blob/main/docs/adr/0002-engine-moves-downstream-unchanged.md)
(the engine moves downstream unchanged) and [0003](https://github.com/saulpatinojr/HCW-CloudCrawler_App/blob/main/docs/adr/0003-the-addon-never-calls-azure.md)
(only the App and the website call Azure MCP). This repository's own decisions are in `docs/adr/`.

## Open upstream decisions that affect this repository

| App ticket | What it is | Why it matters here |
| --- | --- | --- |
| [7](https://github.com/saulpatinojr/HCW-CloudCrawler_App/issues/7): tag and release `v0.1.0` | Done 2026-10-26 | The engine is adopted here (see "First adoption"). |
| [8](https://github.com/saulpatinojr/HCW-CloudCrawler_App/issues/8): no sign-in on the App's `/api` and `/mcp` | The "human only" gate is a non-empty `actorId` today; an authentication model needs an owner decision | The caller classes and identity model it picks may change the tool contract this repository must match. Here, identity stays the website's job (asserted claims only); watch for a contract change. |
| [9](https://github.com/saulpatinojr/HCW-CloudCrawler_App/issues/9): protect `main` and tags | Partly done: pull request plus six checks, `v*` tags locked, but no approving review is required and `CODEOWNERS` still has placeholders | None directly. |
| [13](https://github.com/saulpatinojr/HCW-CloudCrawler_App/issues/13): GUID-scan false alarm | Fixed for bytecode; "scan only tracked files" is not done in the App | This repository already scans only files git lists. |
| [54](https://github.com/saulpatinojr/HCW-CloudCrawler_App/issues/54): Terraform state and plan readers | The engine 0.1.0 stores `tf-state` and `tf-plan` evidence redacted and unparsed (`NORMALISED_KINDS` holds only `arg-export` and `azure-mcp-result`), so no detector reads Terraform | The website row promises Terraform. This edition accepts the two kinds and reports claims about them as `unknown`; reading them is engine work and goes upstream first. |
| [53](https://github.com/saulpatinojr/HCW-CloudCrawler_App/issues/53): the secret-shape pattern is quadratic on repeated `eyJ` | The engine's redaction runs it over every string of an upload; a 64 KB string of `eyJ` repeats held the process for 1 to 3 s | This edition refuses more than 16 `eyJ` in one string (`MAX_TOKEN_STARTS` in `inputs.py`); remove that guard once an engine release fixes the pattern. |
| [16](https://github.com/saulpatinojr/HCW-CloudCrawler_App/issues/16): release hygiene | Proven by the `v0.1.0` release: the three files are there and the wheel's provenance verifies | The first adoption used those files. |
