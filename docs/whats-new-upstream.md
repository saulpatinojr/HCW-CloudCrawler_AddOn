# What's new upstream

The memory file for this repository about its upstream, `saulpatinojr/HCW-CloudCrawler_App` (the App edition). Newest
entries first. Written for a reader, human or Claude session, who has not seen earlier conversations.

## How to use this file

Read it before you change behaviour here, adopt a new engine release, or answer a question about what the App has
done. When the App changes something that reaches this repository, add an entry at the top of "What changed" in the
same change set (the App's `CLAUDE.md` asks for this too), and refresh the table below.

## Current upstream state

Written on 2026-10-26 against the App's release [v0.1.0](https://github.com/saulpatinojr/HCW-CloudCrawler_App/releases/tag/v0.1.0);
the table below was refreshed on 2026-11-05 against [v0.1.1](https://github.com/saulpatinojr/HCW-CloudCrawler_App/releases/tag/v0.1.1),
the release this repository pins since pull request 51.
`v0.1.0` was published
2026-10-26 04:00 UTC from commit `8142b69`. Before that, on 2026-10-24, the App's `main` was at commit `9bad3d1`
(merge of pull request [34](https://github.com/saulpatinojr/HCW-CloudCrawler_App/pull/34), Microsoft Entra sign-in in the App
host); nothing under `packages/` had changed since commit `4ba5add`.

| Question | Answer | How it was checked |
| --- | --- | --- |
| Has the App published a release? | **Yes: `v0.1.0`** (2026-10-26) and **`v0.1.1`** (2026-11-04, the engine pinned here; see the entry of 2026-11-04, 21:30 UTC). Each release has three files, named for its version; for `v0.1.0`: `cloud_crawler_core-0.1.0-py3-none-any.whl`, `cloud_crawler_core-0.1.0.tar.gz` and `cloud-crawler-core.cdx.json` (the software bill of materials). | `gh release view v0.1.0 --repo saulpatinojr/HCW-CloudCrawler_App`; App ticket [7](https://github.com/saulpatinojr/HCW-CloudCrawler_App/issues/7) |
| What does `core-update.yml` do today? | It reads the `# CORE_REF v0.1.1` line now in `pyproject.toml` and compares it with the App's latest release. At `v0.1.1` it reports "already at v0.1.1" and stops; when the App tags a newer release it opens the bump pull request, moving the pin and the version line of the engine's static metadata (marker `# CORE_METADATA`, see "First adoption", the paragraph after item 7) together. Since 2026-10-31 it does this in **two jobs**: `bump` runs the new engine through this edition's lint and tests with no secret; `pull-request` runs no project or engine code, regenerates `pyproject.toml` and `uv.lock` itself, refuses the first job's files unless they match exactly, and only then uses the App key (see the entry of 2026-10-31 below). | `.github/workflows/core-update.yml`; the first adoption added the line by hand (see "First adoption", done) |
| Engine version in the App | `cloud-crawler-core` 0.1.1; the App edition is also 0.1.1 | Read from the `v0.1.1` release on 2026-11-05 |
| What this repository pins | **`cloud-crawler-core` 0.1.1**, by release-asset URL on one line of `pyproject.toml`, with the wheel's sha256 `45a5def595b2de85f0d07693bc4e8fcdd4c6afd65a052d4a5fa3288a66012edc` recorded in `uv.lock`. On 2026-11-05 a fresh download of the release asset had that sha256 and its build provenance verified with `gh attestation verify` (signer: the App's `publish-core.yml` at `refs/tags/v0.1.1`). Before pull request 51 the pin was 0.1.0 (sha256 `25a7abfc…`, verified the same way on 2026-10-26). | `gh release download`, `sha256sum`, `gh attestation verify ... --repo saulpatinojr/HCW-CloudCrawler_App` on 2026-11-05 |
| Does the engine's log-word list match the lab's? | **No, and it is not copied any more.** The old copy of the engine's redaction module had drifted: ten words that only the lab logs (`session_opened`, `session_closed`, the five `turnstile_*` outcomes, `unsupported_media_type`, `arg-json`, `arg-csv`) are not in the engine's list. `security/redaction.py` is now a thin module: the engine's `scrub`, `VisitorDataError` and guard, plus those ten words. | `tests/security/test_engine_adoption.py` |
| Compatible with this repository's pins? | **Yes, with the 0.1.1 wheel pinned here.** The engine 0.1.1 declares `Requires-Python: <3.16,>=3.14.6`; this repository requires `>=3.15.1,<3.16` since it followed the website to the Python 3.15 line (the entry of 2026-11-03 below). The earlier 0.1.0 wheel (`<3.15`) refused Python 3.15, which is why the move waited for the release. Everything else still holds: the engine requires only `pydantic>=2.14,<3`; this repository pins `pydantic==2.14.2`; the engine imports no cloud SDK and nothing that opens a connection (checked here by walking its installed source). | `pip install` of the release wheel on `python:3.15.2-slim-trixie`, the Docker build and the full suite on 2026-11-03 |
| Azure MCP Server | Pinned to 3.0.0 in the App (ADR 0001). **This repository never calls it.** | App ADR 0001 and 0003 |

## What changed

### 2026-11-05: release 0.3.0 of this edition is prepared (nothing new upstream)

- Nothing changed upstream: the App's latest release is still `v0.1.1`, and `core-update.yml` reports "already at
  v0.1.1". This repository's release pull request moves its own version to `0.3.0` (`pyproject.toml`, `__version__`,
  `uv.lock`), folds the changelog, and adds the release guard `scripts/check_release_version.py` so that the dry run
  of `publish-images.yml` refuses everything a tag would be refused for (`CHANGELOG.md`, `[0.3.0]`). The image that
  the tag `v0.3.0` publishes is the first with engine 0.1.1, so it is the first that reads Terraform; the lab host's
  digest bump and the website row's Terraform wording follow it ([issue
  29](https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/issues/29)).

### 2026-11-05: the HCW Main Admin App is also used by two App repositories (credential notes only)

- On 2026-11-04 the lockfile workflow upstream (`HCW-CloudCrawler_App`, this edition's App) and in `HCW-CloudAssessor_App` were changed to push Dependabot's regenerated
  lockfile exports with the HCW Main Admin GitHub App, the App this repository's `core-update.yml` uses ([HCW-CloudCrawler_App#71](https://github.com/saulpatinojr/HCW-CloudCrawler_App/pull/71), [HCW-CloudAssessor_App#87](https://github.com/saulpatinojr/HCW-CloudAssessor_App/pull/87); owner decision on [HCW-CloudCrawler_App#70](https://github.com/saulpatinojr/HCW-CloudCrawler_App/issues/70)). Once the owner installs it there, the App is on six repositories, not four.
- **Reaches this edition? Only the notes.** No engine, pin, workflow behaviour or test changes here. Those two
  repositories hold a separate private key as Dependabot secrets, so rotating this repository's key is unchanged. The
  `core-update.yml` comment and `VALIDATION.md` now say where the App is installed, and the accepted-risk note says a
  stolen key could reach those two repositories as well, whose `main` still needs an approved pull request.

### 2026-11-04, 21:30 UTC: `v0.1.1` is tagged and this pull request pins it

- The App tagged [`v0.1.1`](https://github.com/saulpatinojr/HCW-CloudCrawler_App/releases/tag/v0.1.1) on 2026-11-04 (tag run
  [41914618418](https://github.com/saulpatinojr/HCW-CloudCrawler_App/actions/runs/41914618418): build, attest and release
  green). The pin moved with `scripts/bump_core_pin.py bump --from v0.1.0 --tag v0.1.1`; `uv.lock` records the wheel's
  sha256 `45a5def595b2de85f0d07693bc4e8fcdd4c6afd65a052d4a5fa3288a66012edc`, the same value as a fresh download of the
  release asset, re-locked with CI's uv 0.11.32 on CPython 3.15.2; `bump_core_pin.py check-lock` against this branch's
  own previous lock reports "only cloud-crawler-core moved".

### 2026-11-04, later the same day: this repository is adapted to engine `0.1.1` (issue 29)

- Nothing new upstream since the entry below (the App's `main` is still `b8a238f`, `v0.1.1` still not tagged). This
  repository did the adaptation that entry describes, on the branch `fix/python-315-base`, so that the bump pull
  request for `v0.1.1` comes out green:
  - The four tests that failed with 0.1.1 are rewritten against real-shaped Terraform documents
    (`tests/terraform_documents.py`: a state with a zone-redundant storage account, a SQL database that is not, an
    unmapped resource group and a data source; a plan with an update, a create without an Azure id, an update whose
    `env` tag is only known after apply, and a delete). They assert what the engine now reads: rows, correlations by
    Azure id or Terraform address, the content-free summary, `unknown` with its reason where the document cannot
    answer, and that a resource a plan creates (no Azure id) lies outside a decision scoped to a subscription.
  - `evidence.py` describes a Terraform file as read, with a note per kind (a plan is "what Terraform would build")
    and the engine's `terraform` summary; `docs/api.md`, `README.md`, `samples/README.md`, `web/index.html` and
    `web/app.js` say the same.
  - The `MAX_TOKEN_STARTS` guard in `inputs.py` is removed (App ticket 53 is fixed in 0.1.1: `_TOKEN_IN_RUN` in the
    engine's `redaction.py`, checked in the App source at `b8a238f`), and the two tests that proved the refusal now
    prove the same hostile upload is accepted in linear time with no thread stalled.
- **Still waiting on the tag:** the pin line and `uv.lock` stay at `v0.1.0` (never pin a wheel built here). When the
  owner tags `v0.1.1`, `core-update.yml` opens the bump pull request; with this adaptation merged first, that bump
  should be `compatible`. Then a new add-on release, the lab host's digest bump, and the website row's `terraform`
  tag and "or your Terraform" summary restored together with the copy in `docs/website-integration/integration-guide.md`
  (issue 29's remaining boxes).

### 2026-11-04: the App prepared engine `0.1.1` (not tagged yet): it accepts Python 3.15 and reads Terraform, so taking it is an adaptation, not a pin swap

- The App's `main` is at commit `b8a238f` (pull request
  [67](https://github.com/saulpatinojr/HCW-CloudCrawler_App/pull/67), merged 2026-11-04): version `0.1.1` in every
  place the release check reads, a dated `[0.1.1] - 2026-11-03` changelog section, and `requires-python =
  ">=3.14.6,<3.16"` in the engine and the App. The tag `v0.1.1` did not exist when this was written; pushing it is the
  owner's step. When it does, fill in here: release URL `https://github.com/saulpatinojr/HCW-CloudCrawler_App/releases/tag/v0.1.1`
  (to be confirmed), and the wheel's sha256 from the release notes (to be filled; see the next point).
- **The wheel was built here, in advance.** On 2026-11-04 the engine wheel was built from that commit exactly as the
  App's `publish-core.yml` builds it (Python 3.14, uv 0.11.32, `uv build --no-create-gitignore --package
  cloud-crawler-core`, in a throwaway container): `cloud_crawler_core-0.1.1-py3-none-any.whl`, sha256
  `14e0fa05cb6e451c4323f773b017820f38e6282576584e2225ed5ee46ce6eb3c`, 24 files, `Requires-Dist: pydantic<3,>=2.14`,
  `Requires-Python: <3.16,>=3.14.6` (the App's own `scripts/verify-core-wheel.py` accepted it). Hatchling builds are
  reproducible, so the release asset should carry the same digest; still, compare the asset's sha256 with the release
  notes and with `gh attestation verify` before `uv lock` records it, as the first adoption did. Do not pin a wheel
  built here: the pin is always the release asset (`bump_core_pin.py` builds the URL from the tag).
- **What was proven with that wheel (local, 2026-11-04, Docker Desktop `desktop-linux`):** with the pin pointed at the
  local wheel, `uv lock --no-build --upgrade-package cloud-crawler-core` (uv 0.11.32) recorded it, the image built on
  `python:3.15.2-slim-trixie`, and every check of `ci.yml`'s `image` job passed by hand: `import azure` fails, the
  container refuses an identity endpoint, uid 10001, the hardened start with the upload round trip (`smoke.py`), Python
  3.15.2 equals `BASE_PYTHON_VERSION`, licence label `MIT`. So the Python 3.15 block described in the entry below is
  lifted by this release: `pip install --require-hashes` accepts the wheel and
  `test_wheel_accepts_every_python_the_project_allows` passes.
- **What changed in the engine, and what it breaks here** (`git diff v0.1.0..main -- packages/cloud-crawler-core`,
  27 files, 5,016 lines added):
  1. **The engine reads Terraform state and plan** (App ticket
     [54](https://github.com/saulpatinojr/HCW-CloudCrawler_App/issues/54), pull request
     [60](https://github.com/saulpatinojr/HCW-CloudCrawler_App/pull/60)). `NORMALISED_KINDS` now holds `tf-state` and
     `tf-plan`; a document is bounded, parsed through a provider-type table (hashicorp/azurerm only), rows are made
     for the types the table knows, and the stored payload is the rows plus a content-free summary. A state or plan
     that is not real Terraform (the stubs these tests use, `{"version": 4, "resources": [{}]}`) is now refused with
     `invalid_request`, where 0.1.0 stored it unread. New field `NormalizedResource.notCarried` (identity, tags or
     zones the evidence cannot answer, for example a plan whose tags are only known after apply): a detector or scope
     that reads such a field answers `unknown` instead of "absent". In the drift engine, a plan row never replaces a
     row of another kind and never closes a contradiction. **Here, four tests fail with 0.1.1 for these reasons
     (run on 2026-11-04 on Python 3.15.2 in a container):**
     `tests/unit/test_evidence.py::test_terraform_state_and_plan_are_recorded_but_not_read_by_this_engine`,
     `tests/unit/test_upload_api.py::test_several_files_and_terraform_are_accepted_and_the_response_says_what_was_read`,
     `tests/unit/test_upload_api.py::test_a_claim_nothing_can_read_is_unknown_never_a_guess` and
     `tests/security/test_upload_hardening.py::test_claims_times_resources_is_capped_before_the_engine_evaluates_anything`
     (its comment "Terraform files read into no resources, so they never count against it" is no longer true). The
     words "this version of the engine does not read Terraform yet" in `src/cloud_crawler_lab/evidence.py`,
     `docs/api.md`, `README.md`, `web/index.html` and `web/app.js` become wrong at the same moment. That is
     [issue 29](https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/issues/29) here: the bump pull request that
     `core-update.yml` opens for `v0.1.1` will come out red and labelled `needs-adaptation`, and the adaptation (tests
     with real-shaped Terraform documents, the route's note, the pane wording, then the website row) is done on it or
     on a branch of its own before it merges. Everything else in the suite passed with the new engine (587 passed;
     the 57 remaining failures in that run came from the temporary local-wheel pin, which is not the GitHub URL shape
     that `tests/unit/test_bump_core_pin.py` and six tests in `tests/security/test_engine_adoption.py` expect, and
     disappear with the real pin).
  2. **The secret-shape pattern is linear and the glued-token regression is fixed** (App ticket
     [53](https://github.com/saulpatinojr/HCW-CloudCrawler_App/issues/53), pull requests
     [59](https://github.com/saulpatinojr/HCW-CloudCrawler_App/pull/59) and
     [61](https://github.com/saulpatinojr/HCW-CloudCrawler_App/pull/61)). Once 0.1.1 is pinned, the `MAX_TOKEN_STARTS`
     guard in `src/cloud_crawler_lab/inputs.py` (and its tests) can go, as the table of open decisions below said.
  3. **Dependencies and the static metadata are unchanged:** the wheel still requires only `pydantic>=2.14,<3`, so the
     `CORE_METADATA` entry needs only its version line moved, which `bump_core_pin.py` does.
- **App-only, nothing reaches here:** the appliance now refuses to start without sign-in on a non-loopback address,
  the optional app-role check, the real-tenant sign-in record and the new guide pages. This repository runs its own
  server, never the appliance's.

### 2026-11-03: this repository moved to Python 3.15; the engine 0.1.0 does not accept it yet

- Nothing changed upstream. This repository followed the website's lab base to `python:3.15.2-slim-trixie`
  ([saulpatinojr/HCW-HybridCloudWorks#1386](https://github.com/saulpatinojr/HCW-HybridCloudWorks/issues/1386)) and
  now requires Python `>=3.15.2,<3.16`.
- What it means for the engine: the pinned release, `cloud-crawler-core` 0.1.0, says `Requires-Python: <3.15,>=3.14.6`
  (read from the wheel's `METADATA`), and `packages/cloud-crawler-core/pyproject.toml` on the App's `main` says the
  same. `pip` refuses a wheel whose range excludes the running Python, so the image build stops at its `pip install`
  step with `Package 'cloud-crawler-core' requires a different Python: 3.15.2 not in '<3.15,>=3.14.6'`, and
  `test_wheel_accepts_every_python_the_project_allows` fails for the same reason. The next App release needs
  `requires-python` to cover 3.15; `core-update.yml` then opens the bump pull request as usual, and both go green with
  it. Do not work around this with `--ignore-requires-python`: the refusal is the engine's own statement about what it
  was tested on.

### 2026-10-31: `core-update.yml` split into two jobs (this repository's change, not the App's)

- Nothing changed upstream. This repository changed how it adopts the next upstream release: the job that runs the new
  engine's code (the compatibility check) no longer holds the GitHub App key. The second job checks the first job's
  `pyproject.toml` and `uv.lock` against ones it made itself, without running any engine code, and only then opens the
  pull request. The same split was merged in the Cloud Assessor and Network Eyes add-ons on 2026-10-31.
- What it means for the next release: the bump pull request looks the same (it changes `pyproject.toml` and `uv.lock`
  only, labelled `compatible` or `needs-adaptation`). If the run goes red in the `pull-request` job with "the bump
  artifact is refused", the two jobs disagreed; read that job's log before anything else, and do not re-run it
  hoping for green. The pin and the `CORE_METADATA` line are now moved by `scripts/bump_core_pin.py` (an exact
  replacement) instead of `sed`, so the two lines must keep exactly the shape shown in "First adoption", item 2, and the
  metadata line `version = "<version>"  # CORE_METADATA` (two spaces before the `#`).
- Not yet proven: the two-job layout has not run on GitHub, because no release newer than `v0.1.0` exists. Keep the
  repository variable `CORE_AUTOMERGE` unset (or `false`) until it has opened one bump pull request that a person has
  looked at.

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
2. In `pyproject.toml`, added to `dependencies`, on one line (`scripts/bump_core_pin.py`, which moves it, expects exactly this shape; until 2026-10-31 the workflow used `sed`):
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
   **Update, 2026-10-26: the upload route is built** ([issue 16](https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/issues/16),
   [ADR 0004](adr/0004-the-upload-route.md), [`docs/api.md`](api.md)); it is the content of release `0.2.0`, and
   `CAPABILITIES` now lists it. It calls the engine's `ingest` and `evaluate_decision` and `bundle` as published, and builds
   the decision record the way the App's `adr_create` tool does (the engine does not contain that step: it lives in the
   App's `mcp_server.py`, so the lab keeps its own copy with limits, and the App's golden verdicts hold it to the same
   answers). Still not done: the MCP server surface and the trusted-caller session API (later releases).
6. Ran `uv sync --all-packages`, `uv run ruff check . && uv run ruff format --check .` and
   `uv run pytest -q --cov=src --cov-fail-under=85` (70 passed, 95 percent), and built the image locally.
7. Updated `CHANGELOG.md`, `VALIDATION.md` and the "Current upstream state" table here.

**Missed at adoption, added 2026-10-27 ([issue 33](https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/issues/33)): the
engine's metadata.** Pinning the wheel (the Python package file) by address made Dependabot's Python job fail for every
package, because uv asked that address for the wheel's metadata each time it rebuilt the lock. `pyproject.toml` now
carries a `[[tool.uv.dependency-metadata]]` entry for the engine (its version line ends in `# CORE_METADATA`),
`core-update.yml` moves that version with the pin, and a test compares the entry's dependency list with the installed
wheel. So an engine release that changes the engine's dependencies turns the bump pull request red until the list is
updated by hand. Runbook: "Keeping Dependabot's Python updates working" in `docs/operations/runbook.md`.

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
| [54](https://github.com/saulpatinojr/HCW-CloudCrawler_App/issues/54): Terraform state and plan readers | **Released upstream** in `v0.1.1` on 2026-11-04 (pull request 60) and pinned here since pull request 51; the engine reads `tf-state` and `tf-plan` | The website row will promise Terraform again. This edition is adapted to 0.1.1 ([issue 29](https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/issues/29); entries of 2026-11-04 below), release 0.3.0 carries it (entry of 2026-11-05), and the row's Terraform wording is restored once the lab host runs the `v0.3.0` image. |
| [53](https://github.com/saulpatinojr/HCW-CloudCrawler_App/issues/53): the secret-shape pattern is quadratic on repeated `eyJ` | **Fixed upstream** (pull requests 59 and 61, in engine 0.1.1, released 2026-11-04 and pinned here). In the earlier 0.1.0 a 64 KB string of `eyJ` repeats held the process for 1 to 3 s | The `MAX_TOKEN_STARTS` guard in `inputs.py` is removed (pull request 51); `tests/security/test_upload_abuse.py` proves the hostile string is accepted in linear time. |
| [16](https://github.com/saulpatinojr/HCW-CloudCrawler_App/issues/16): release hygiene | Proven by the `v0.1.0` release: the three files are there and the wheel's provenance verifies | The first adoption used those files. |
