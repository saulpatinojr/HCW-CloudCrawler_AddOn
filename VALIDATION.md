# Validation

What was executed for this edition and what was not, per run. "Here" is the authoring container (no Docker daemon;
PyPI reachable through a proxy). Dates are the run date.

## Run 2026-10-21 (0.1.0 skeleton, initial)

Toolchain: Python 3.14.6 (`uv python install 3.14`; `.python-version` 3.14.6), uv 0.11.32. Resolved pins: fastapi
0.143.0, uvicorn 0.54.0, pydantic 2.14.1 (pydantic-core 2.50.1, starlette 1.9.0, anyio 4.15.1, h11 0.16.0, click
8.5.0, idna 3.20, annotated-types 0.8.0, annotated-doc 0.0.5, opentelemetry-api 1.45.1, typing-extensions 4.16.0,
typing-inspection 0.4.4); dev pytest 9.1.1, pytest-cov 7.1.0, ruff 0.17.0, httpx 0.28.1, pip-audit 2.10.1; build
hatchling 1.32.4. `uv.lock` is committed; 14 third-party runtime packages, none Azure. There is no engine yet: the
`cloud-crawler-core` wheel is adopted from `HCW-CloudCrawler_App` at its first release (ADR 0001).

| Check | Executed here | Result |
|---|---|---|
| `uv sync --all-packages` | yes | 51 packages resolved and installed |
| `uv run ruff check . && uv run ruff format --check .` | yes | clean (44 files) |
| `uv run pytest -q --cov=src --cov-report=term-missing --cov-fail-under=85` | yes | 62 tests passed; coverage 95% (481 statements, 23 missed; gate 85). `__main__.py` is covered only by its subprocess tests, which coverage does not trace |
| `uv run pytest tests/security tests/contract -q` | yes | 20 passed (edition boundary incl. fresh-process refusal and the no-outbound-import walk, no secrets and no real identifiers, content-free logs, health shape and pane protocol) |
| Live server: `CC_ALLOW_NO_TURNSTILE=1 PORT=8099 CC_SITE_ORIGINS=https://hybridcloudworks.com uv run python -m cloud_crawler_lab`, then `GET /api/health`, `GET /`, `GET /api/nothing`, `POST /api/health` | yes | health 200 `ok:true id:cloud-crawler version:0.1.0 edition:lab capabilities:[health,pane] azureConnectivity:disabled-by-design`, headers `X-Addon-Id`, `X-Addon-Version`, CSP with `frame-ancestors 'none'`, `X-Frame-Options: DENY`, `Cache-Control: no-store`; index 200 `text/html`; 404 and 405 in the error envelope. Log lines: `startup`, `turnstile_disabled` (warning), `shutdown`; counts, flags and event names only |
| `IDENTITY_ENDPOINT=http://169.254.169.254 uv run python -c "import cloud_crawler_lab.app"` | yes | exit 1 with `EditionBoundaryError: refusing to start: identity environment present (IDENTITY_ENDPOINT)`; `python -m cloud_crawler_lab` under `MSI_ENDPOINT` exits 3 with one scrubbed `startup_refused` line |
| `uv export --frozen … \| uv run pip-audit -r … --strict` | yes | no known vulnerabilities (14 packages) |
| `uv lock --check` | yes | lock current with `pyproject.toml` |
| `versions.env` vs every `FROM` | locally by the same shell logic as `ci.yml` | both `FROM` lines equal `BASE_IMAGE@BASE_DIGEST` |
| Docker image build (`infrastructure/docker/Dockerfile`) | **no**, CI only | no daemon here; `ci.yml` builds the image on every pull request and proves `import azure` fails, the container exits under `IDENTITY_ENDPOINT` and runs as uid 10001; `publish-images.yml` repeats that, runs the hardened health check, scans with Trivy, and pushes only when `DOCKERHUB_ENABLED` is `true` |
| Trivy scan, SBOM, provenance, attestation | **no**, CI only | as above |
| uv image digest in the Dockerfile vs `UV_VERSION` | **no**, CI only | `ci.yml` resolves the digest from the registry; the Dockerfile carries the digest the Cloud Assessor AddOn verified for 0.11.32 |
| Human verification against the real siteverify endpoint | **no** | mocked in `tests/unit/test_security_modules.py`; no upload route exists yet, so the verifier is not wired to a request |
| Lab-host deployment, reverse-proxy route, website pane, catalogue row | **no** | owner steps and a website pull request once a digest exists; the row does not exist yet |
| CodeQL, gitleaks, dependency review, Qlty, CodeRabbit | **no**, CI only | `codeql.yml`, `dependency-review.yml` (template), `security.yml`; the review apps are connected by the owner (`docs/TEMPLATE.md` step 2 of the template, now removed) |

## Run 2026-10-26 (engine `v0.1.0` adopted)

Toolchain: Python 3.14.6, uv 0.12.0 locally for `uv sync` and `uv run`; `uv lock` was run with uv 0.11.32 (the version CI
pins) and `uv lock --check` passes with it. Windows host, so the container checks used Docker Desktop (context
`desktop-linux`, local).

| Check | Executed here | Result |
|---|---|---|
| Release asset hash | yes | `sha256sum` of a fresh `gh release download` of `cloud_crawler_core-0.1.0-py3-none-any.whl` is `25a7abfcec50b0f85cb427145a1fd7fb57898bd09cfc3483edad8a042e5e7be3`, equal to GitHub's digest for the asset and to the hash in `uv.lock` |
| `gh attestation verify <wheel> --repo saulpatinojr/HCW-CloudCrawler_App` | yes | exit 0; signed by `publish-core.yml` at `refs/tags/v0.1.0` (commit `8142b69`), SLSA provenance v1; the same file is also attested from three runs on `main` (rehearsals); a CycloneDX attestation exists against the wheel |
| `uv lock`, `uv lock --check` (uv 0.11.32) | yes | adds `cloud-crawler-core` 0.1.0 with the sha256 above; current |
| `uv sync --all-packages` | yes | needed `[tool.hatch.metadata] allow-direct-references = true` (hatchling refuses a URL dependency otherwise) |
| `uv run ruff check . && uv run ruff format --check .` | yes | clean (47 files) |
| `uv run pytest -q --cov=src --cov-fail-under=85` | yes | 70 passed; coverage 95% (includes the new `tests/security/test_engine_adoption.py`: the pin shape, the installed version, the sha256 in the lock, the engine's imports, the log-word guard) |
| `docker build` of the lab image, then in disposable containers: `import cloud_crawler_core` works, `import azure` and `import msal` fail, the image refuses to start under `IDENTITY_ENDPOINT`, uid 10001, the read-only/cap-drop run answers `/api/health` 200 (`capabilities: [health, pane]`, `azureConnectivity: disabled-by-design`) | yes, local | all as listed; the task image was removed afterwards |
| `uv export ... --no-emit-package cloud-crawler-core` then `pip-audit --strict` (what `security.yml` now runs) | yes | no known vulnerabilities in the 14 third-party packages; with the engine left in, `pip-audit --strict` fails ("not found on PyPI"), which is how CI showed it on the pull request |
| Trivy scan, SBOM, provenance and attestation of the image, the push | **no**, CI only | `publish-images.yml` on a tag |
| CodeQL, gitleaks, dependency review, CodeRabbit | **no**, CI only | run on the pull request |

## Run 2026-10-26 (release 0.1.0 prepared; publish dry run)

| Check | Executed here | Result |
|---|---|---|
| `gh workflow run publish-images.yml --ref release/v0.1.0` (manual run, [run 40268798058](https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/actions/runs/40268798058)) | yes, in CI | success: the image built with the engine in it, the in-image boundary checks passed (`import azure` and `import msal` fail, no pip, uid 10001, refuses an identity endpoint, hardened health check answers), Trivy (HIGH/CRITICAL, fixed only) passed, and the push, provenance, SBOM and attestation steps were **skipped** with a notice that the ref is not a `v*` tag |
| Push, provenance, SBOM and SLSA attestation of the image, and the image digest | **no** | only a `v*` tag can push (the Docker connection trusts tags only); this is the tag `v0.1.0` in issue [17](https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/issues/17) |
| `guide-drift.yml` on `main` before this change | yes, in CI | success, 12 fields compared ([run 40267695699](https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/actions/runs/40267695699)); this change edits the guide's prose only, not the catalogue-row copy |

## Run 2026-10-26 (the upload route, issue 16)

Toolchain: Python 3.14.6, uv 0.12.0 locally (CI uses uv 0.11.32). Windows host with Docker Desktop (context `desktop-linux`,
local engine). Local container runs used a task-specific tag (`img-cc-lab-addon:task-upload-route`) and disposable containers
(`--rm`, loopback ports only), all removed afterwards. "CI" means a manual run on the branch before the pull request; none of
those runs can push an image.

| Check | Executed here | Result |
| --- | --- | --- |
| `uv run ruff check . && uv run ruff format --check .` | yes | clean (66 files) |
| `uv run pytest -q --cov=src --cov-fail-under=85` | yes, and in CI | **284 passed, coverage 97.54%** (gate 85). 71 tests were there before; 209 are in the new or rewritten modules: the upload API, the bounded reader, the decision and evidence checks, the store, the pane's static contract, the hardening and abuse suites and the acceptance test |
| The new tests against the old source (`origin/main` in a scratch checkout, new tests copied in) | yes | the 8 new test modules cannot be imported (the modules do not exist); of the other 91 tests, 26 fail (the route list, the capability list, the pane, the acceptance verdicts, the settings) and 65 pass |
| Acceptance: the App's golden verdicts for the sample estate through the upload route | yes | the same verdict for every resource as the App's own acceptance tests (`tests/acceptance/golden/`, copied unchanged): supported 3, contradicted 2, unknown 0, not applicable 8, score 60.0, coverage 1.0 for the zone-redundancy decision; all six detectors of the wave-one baseline |
| `uv lock --check`; `uv export ... --no-emit-package cloud-crawler-core \| pip-audit --strict` (as `security.yml`) | yes | lock current; no known vulnerabilities |
| hadolint (the image `ghcr.io/hadolint/hadolint` already on this machine, by id) on the Dockerfile | yes | exit 0, before and after the change. No workflow runs hadolint (CodeRabbit does) |
| actionlint (image already on this machine) on `ci.yml` and `publish-images.yml`, shellcheck off | yes | no finding except the repository-wide runner label `ubuntu-26.04` that this older actionlint does not know; `bash -n` on the two edited steps is clean |
| `docker build` of the lab image; in-image boundary checks as in `ci.yml` | yes, local | `import azure` and `import msal` fail, `cloud_crawler_core` 0.1.0 imports, the image refuses to start under `IDENTITY_ENDPOINT`, uid 10001, no pip; `/app/samples` holds the four JSON files, root-owned |
| `infrastructure/docker/smoke.py` run inside a hardened container (`--read-only`, no tmpfs, `--cap-drop ALL`, `no-new-privileges`, `--memory 512m --memory-swap 512m --pids-limit 256 --cpus 1`) | yes, local and in CI | every check `ok` (health with the new capabilities, the pane, the four samples, `README.md` 404, an upload of the sample, the owner reads it, anyone else 404, `NOT-AN-AUDIT.md`, delete, gone); `OOMKilled=false`; the container's log lines are counts and fixed words (zero matches for `hcw-sample`, a GUID, the owner token or a region) |
| Abuse run against that container (script not committed): 5 MB of empty arrays, deep nesting, 5 MB + 1 byte, a zip, a YAML content type, a 4.5 MB / 5,000-row / 5-claim upload (25,000 findings), three of those at once while `/api/health` is polled | yes, local | refused in 0.05 s with `too_complex` (422), 422, 413, 400, 415; the big upload answers 201 in 1.4 s with 1,000 findings listed of 25,000 and exact counts; with three at once one waited and was answered 503 politely, the other two 201; `/api/health` answered 200 in 0.01 to 0.12 s throughout; **peak memory 269 MiB of 512 MiB**; healthy afterwards |
| Memory of one evaluation by shape (`tracemalloc`, in process) | yes | 25,000 findings: 120 MB; the worst accepted shape (one row with 95,000 tiny objects): 55 MB (the first version accepted 385,000 of them and used 229 MB per evaluation, found by the security review); 600 strings of 8 KB: 15 MB |
| Real browser (Playwright with its Chromium, from the website repository's `node_modules`, headless; script not committed) against a local lab | yes, local | **34 of 34 checks pass**: the sample flow end to end (summary cards, the not-an-audit line and its full text, findings with a filter, review notes, the draft decision record, the report), Markdown and JSON downloads, two-click delete, own files and a decision file, a Terraform plan listed with the not-read note, bad files refused in the browser, a lab refusal explained by claim position, no horizontal scroll at 390 px, and the pane inside a sandboxed frame (`allow-scripts allow-same-origin allow-forms`, no `allow-modals`) posting `loading, ready, working, ready` to the site origin only, with delete working there and no console errors |
| The human-verification widget with the vendor's public test keys, local lab | yes, local | the verification script loads under the lab's CSP, the widget delivers a token and the pane enables the button, and the lab calls the verification endpoint with the test secret and enforces the result (`403`, code `action-mismatch`: the test keys do not echo the action `cloud-crawler-upload`, so a successful verification is **not** shown) |
| `gh workflow run ci.yml`, `publish-images.yml`, `guide-drift.yml` on the branch | yes, in CI | all three succeed: [ci](https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/actions/runs/40276688270) (lint, test with 284 passed and 97.54%, image with the round trip), [publish-images dry run](https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/actions/runs/40276690648) (build, boundary checks, the round trip, Trivy HIGH/CRITICAL fixed-only, push skipped because the ref is not a `v*` tag), [guide drift](https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/actions/runs/40276693238) (12 fields compared, in step) |
| Independent security review (`python-security-reviewer`, read-only) and container review (`container-security-reviewer`, read-only) | yes | first pass: 1 blocker, 3 high, 3 medium, 5 low findings and a list of suggestions, all addressed or recorded below; second pass after the fixes is recorded in the pull request |
| Real human verification (a site key and secret of the lab host), the lab host and its proxy, the website's frame, a real estate's export | **no** | owner steps and the website's pull request; nothing here proves them |

What the security review found and what was done (full detail in the pull request): a validation-error amplification
(250,000 bad entries in a 4 MB decision built 1.3 GB of pydantic errors: fixed with a size budget before validation and by
dropping the input from the errors), a quadratic pattern in the engine's secret redaction (1 to 3 s per 64 KB string of
`eyJ` repeats: mitigated by refusing more than 16 `eyJ` in a string, engine fix is [App issue 53](https://github.com/saulpatinojr/HCW-CloudCrawler_App/issues/53)), memory (documents of
hundreds of thousands of tiny objects: bounds lowered, uploads in memory capped at four before the body is read,
evaluations on their own threads), one client evicting everyone's results (per-client share), a pane delete that needed a
dialog a sandboxed frame may not open (two-click button), a null claim parameter that became a 500, a client disconnect
that was an unhandled error, a cancelled request that released its evaluation slot early, and the rate-limit key
(X-Forwarded-For is now used only when it is an IP address; the lab host's Caddy ignores an incoming value by default).

## Run 2026-10-26 (the upload route: an independent second check)

A second implementation of the same issue, written in parallel and never pushed, was reviewed by an independent read-only
security reviewer. Its findings were turned into hostile inputs and sent to this route, which was then mutation-checked.
Same toolchain as the run above; the in-process runs used the repository's own environment, so no second one was built.

| Check | Executed here | Result |
| --- | --- | --- |
| The review's hostile inputs sent to `POST /api/uploads` in process: 81 KB and 2 MB of `eyJ` in a tag, a 4 MB tag value read by 10 claims, an 8,500-entry scope list, 5,000 rows with 5 claims, 600,000 empty rows, NaN, nesting 3,000 deep | yes, local | the first seven are refused in under 0.1 s with `too_complex` (422) or `invalid_request` (400) and at most 16 MB; the 5,000-row upload is accepted in 2.5 s with a peak of 83 MB. The first draft of the parallel implementation took 2.1 s, 485 MB and 45 s on three of them |
| Text from the export in `report.md` (a newline then `# heading`, an image link, `<script>`, `<img>`, a pipe, a backtick, in a location, an id, a decision title and a claim statement) | yes | **found a gap**: all five markers were present raw in `report.md`. Fixed (`markdown_text`); `tests/security/test_report_markdown.py` holds it and `report.json` still keeps the text |
| Mutation checks: 26 deliberate breaks of the source (verification skipped, fail-closed removed, owner token not compared, expiry never applied, declared size not refused before verification, media type unchecked, rate limit off, row budget lifted, `eyJ` cap removed, NaN accepted, claims times resources uncapped, echoed values not shortened, findings uncapped, markdown not escaped, log code unmapped, exception text logged, evaluation slot never released, decisions stored as accepted, oversize result stored, no eviction at the item limit, non-ASCII digits accepted, an outbound import, an over-long owner token, any file name accepted, `NOT-AN-AUDIT.md` left out, read deadline removed), each followed by the whole suite | yes | 23 caught at first; **3 survived** (declared size before verification, the log-word mapping, the owner-token length cap); `tests/security/test_upload_gate_order.py` closes them and all 26 are now caught. Each file was restored after its run |
| `uv run pytest` (the repository's tests plus the two new modules) with the 85 percent gate | yes | 302 passed, coverage 97.59% |
| Real browser (headless Chromium over the DevTools protocol, no package installed, script not committed) against a local lab, with the local override and without it | yes, local | 22 of 22 checks with the override (the real file picker with a real file, the sample baseline decision, the claims table, 39 findings, review notes, the not-an-audit line, the filter, the draft record, the report, a two-click delete, a refused decision explained, no storage, no console error or policy violation) and 5 of 5 on the closed lab (the pane says uploads are not available until human verification is configured and keeps the button off) |

## Run 2026-10-26 (release 0.2.0 prepared; publish dry run)

Toolchain as in the runs above (Python 3.14.6, uv 0.12.0 locally, CI uses uv 0.11.32). This run prepares the version bump
only; the upload route itself was validated in the run before this one.

| Check | Executed here | Result |
| --- | --- | --- |
| The version in every place that says it: `pyproject.toml`, `uv.lock` (the `cloud-crawler-lab` entry), `__version__` | yes | all `0.2.0`; `uv lock --check` passes; `/api/health` and the `X-Addon-Version` header read `__version__`, and `tests/contract/test_health_shape.py` holds `pyproject.toml` and `__version__` together |
| `uv run ruff check . && uv run ruff format --check .` and `uv run pytest -q --cov=src --cov-fail-under=85` | yes | clean (69 files); 302 passed, coverage 97.59% |
| `gh workflow run publish-images.yml --ref release/v0.2.0` ([run 40311390536](https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/actions/runs/40311390536), commit `c4efbfb`) | yes, in CI | success: the image built, the in-image boundary checks and the round trip inside the hardened container passed (`upload round trip ok`), Trivy (HIGH/CRITICAL, fixed only) passed, and login, push, provenance, SBOM and attestation were **skipped** with the notice that the ref is not a `v*` tag |
| Push, provenance, SBOM and SLSA attestation of the image, and its digest | **no** | only a `v*` tag can push (the Docker connection trusts tags only); `v0.2.0` is the owner's explicit call on issue [17](https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/issues/17). The same dry run on `main`, at the merge commit of this change, is linked from that issue |
| The website's catalogue row is unchanged here | yes | the guide's row copy is untouched; the guide-drift check on this branch compares the same 12 fields |

## Run 2026-10-27 (Dependabot's uv job; issue 33)

Windows host. uv 0.12.0 locally for `uv run`. To reproduce, three more uv versions were installed with `pip` into throwaway
virtual environments outside the repository: 0.13.5 (the version the failed Dependabot job reports using), 0.13.6 (the
newest) and 0.11.32 (the version CI pins; `uvx uv@0.11.32` was also used). Nothing was installed globally. An independent
read-only review of the first version of this change (`infrastructure-pr-reviewer`, which had not seen the author's
conclusions) repeated most of the measurements below and found the problems fixed in the second commit: the metadata entry
no longer sets `requires-python`, the workflow test is scoped to the bump step, the PowerShell commands work in Windows
PowerShell 5.1, the claims about uv versions are qualified, and the wording is plainer. CodeRabbit's review of the pull
request ([pull request 35](https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/pull/35)) then raised four more points,
all checked against the code and fixed in the third commit: requirement extras and URLs were not compared (and
`test_engine_requires_only_pydantic` split the text, so `pydantic [email]` passed), the engine's `Requires-Python` was
not compared with the project's range, any extra was rejected even after the entry listed it, and the runbook did not
say to review a new dependency first.

| Check | Executed here | Result |
| --- | --- | --- |
| The failed Dependabot job's log ([run 40499840932](https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/actions/runs/40499840932), read with `gh run view --log`) | yes | for `ruff`, `fastapi`, `certifi` and `coverage` (the four errors the job reports) the updater ran `uv lock --upgrade-package <package>`; each time the proxy log shows `HEAD` of the engine's release address, `302`, then `HEAD` of a signed `objects.githubusercontent.com` link answered `401`; each ends `private_source_authentication_failure` naming the release address. The engine is not the package being updated in any of them. The job log names uv 0.13.5 |
| The release address from this machine (`curl`) | yes | `HEAD` gives 302 to `release-assets.githubusercontent.com`, which answers `HEAD` and `GET` with 200; `GET` through the redirect downloads 37,822 bytes. **The 401 was not reproduced**; why the signed link refused the `HEAD` is an inference |
| Dependabot's error mapping, read in `dependabot-core` (`uv/lib/dependabot/uv/file_updater/lock_file_error_handler.rb`, on 2026-10-27) | yes | a uv error matching `authentication`, `unauthorized`, `forbidden` or `HTTP status code: 401/403` becomes `PrivateSourceAuthenticationFailure`; the source is never checked for privacy. uv's own error text is not printed in the job log, so that it matched is inferred |
| Cold-cache `uv lock --upgrade-package ruff==0.17.2` on the original `pyproject.toml` and `uv.lock`, four uv versions | yes | 0.13.5 and 0.13.6: one `HEAD` and one `GET` of the engine's address. 0.12.0 and 0.11.32: one `GET`, no `HEAD`. Every run exits 0 from this network, where the `HEAD` answers 200 |
| The same on the files of this change (entry in `pyproject.toml` and in `uv.lock`) | yes | 0.13.5 and 0.13.6: no request to the engine's address. 0.12.0 and 0.11.32: one `GET`. The engine's `source` and sha256 in the lock are unchanged after a re-lock by 0.13.5 |
| `uv lock` and `uv lock --check` with uv 0.11.32 | yes | the lock gains only the `[manifest]` block (7 lines); `--check` passes. A lock written by uv 0.13.5 (`revision = 5`) also passes `--check` under 0.11.32 (the reviewer's run; the sibling add-ons merge such locks) |
| `uv export` with the Dockerfile's flags (`--frozen --format requirements-txt --no-dev --no-emit-project --no-header`) on the old and the new files, uv 0.11.32 | yes | byte-identical (sha256 `e14b95f7e45b3190eb46...` for both; 100 lines, 59 hashes) |
| The wheel's metadata against the entry | yes | the wheel from the release (sha256 equals the one in the lock) says `Requires-Dist: pydantic<3,>=2.14`; the entry says the same. The wheel also says `Requires-Python: <3.15,>=3.14.6`; the entry leaves it out on purpose (Dependabot rewrites every `requires-python` in the lock to the first one, read in `lock_file_updater.rb`) |
| The bump lines of `core-update.yml` (extracted from the file) run on a scratch copy of `pyproject.toml` with a pretend `v0.2.0` | yes | only three things move: the address, the `CORE_REF` marker and the entry's `version`. The reviewer also ran them against a fake `v0.2.0` wheel with an extra dependency served from localhost: `uv lock` recorded the new sha256 and the installed-wheel test went red, as designed. The real bump (a real `v0.2.0` release) was **not** run: none exists |
| The new tests on the original `pyproject.toml` and `uv.lock` | yes | the file now holds 46 cases (8 before this change). On the original files the 6 tests that read the entry fail (`test_engine_has_static_metadata_for_the_pinned_wheel`, `..._carries_the_marker_core_update_moves`, `test_lock_manifest_records_the_same_static_metadata`, `test_static_metadata_does_not_set_requires_python`, `test_every_direct_url_package_in_the_lock_has_static_metadata`, `test_static_metadata_matches_the_installed_wheel`); the other 40 pass: the workflow test, which reads only the workflow, and the unit tests of the comparison helpers |
| The tests of the third commit against the second (f57919f), under three mutations of the real files: the entry's requirement spelled `pydantic [email]>=2.14,<3`; the entry given `provides-extra = ["email"]` that the wheel lacks; the installed wheel's `METADATA` changed to `Requires-Python: >=3.14.8` (an edit inside the worktree's ignored `.venv`, backed up and restored) | yes | the second commit's tests pass all three (15 passed each time: the bugs); the new tests fail each one (`test_static_metadata_matches_the_installed_wheel` and `test_lock_manifest_records_the_same_static_metadata` for the first two, `test_wheel_accepts_every_python_the_project_allows` for the third). Unit cases show a correctly adapted bump that gains an extra passing, and a missing, extra or mismatched extra, version or requirement failing |
| The workflow test on three versions of `core-update.yml` | yes | passes as written; fails when the `sed` and `grep` lines are deleted; fails when they are moved after `uv lock` (the first version of this test passed in all three) |
| The PowerShell commands in the runbook, in Windows PowerShell 5.1.26100 | yes | the run-list command prints empty values without the outer brackets and the right values with them; the wheel-metadata commands work twice in a row (each run has its own folder). An attempt to run a script file with `-ExecutionPolicy Bypass` was refused by the session's safety check and was not repeated; the commands were run inline instead |
| `uvx uv@0.11.32 lock --check` | yes | prints `Resolved 52 packages`, exit 0 (the runbook gives `uvx uv@0.11.32 lock` for the real run) |
| `uv run --frozen ruff check .` and `ruff format --check .` | yes | clean (73 files) |
| `uv run --frozen pytest -q --cov=src --cov-report=term --cov-fail-under=85` | yes | 515 passed, coverage 97.59% |
| `git diff --check`; line endings (`git ls-files --eol`) | yes | clean; every changed file is `i/lf w/lf`, no carriage returns |
| **A Dependabot run on `main` after the change** | **no** | Dependabot version updates run only from the default branch and there is no API to start one from a branch. The next scheduled run is Monday 2026-11-02 06:00 UTC; after the merge, **Check for updates** on the repository's Dependabot page starts one (runbook). Issue 33's last box (a green run, a dependency pull request opened) stays open until that run is seen |
| A `GET` of the signed link from inside Dependabot's network | **no** | not testable here. With the entry, uv 0.13.5 and later asks for nothing at the address while updating an ordinary package; `core-update.yml` (which does download the wheel, from an Actions runner as it did for the first adoption) is unchanged in that respect |
| The Dependabot page's layout ("Check for updates") | **no** | the page needs a sign-in; the steps come from GitHub's documentation |
| Whether Dependabot's image carries the `dependabot-core` code on `main` that was read | **no** | the error mapping and the `requires-python` rewrite were read on `main` on 2026-10-27 |
| CI on the pull request, CodeQL, CodeRabbit | **no** | run on the pull request |

## Run 2026-10-31 (the image's Python matches `BASE_PYTHON_VERSION`)

Linux cloud session, Docker available, uv from `uv sync --all-packages`. The change adds one step to the `image` job of
`ci.yml` ("The image runs the Python that versions.env names (BASE_PYTHON_VERSION)") and a test file for it
(`tests/security/test_ci_image_python_version.py`). Background: the `lint` job proves the `FROM` lines use the pinned
digest, but not which Python that digest carries
([saulpatinojr/HCW-HybridCloudWorks#1386](https://github.com/saulpatinojr/HCW-HybridCloudWorks/issues/1386)).

| Check | Executed here | Result |
| --- | --- | --- |
| `uv run ruff check .` and `uv run ruff format --check .` | yes | clean (74 files) |
| `uv run pytest -q --cov=src --cov-fail-under=85` | yes | 527 passed, coverage 97.59%; 12 of them are the new file's |
| `uv lock --check` | yes | `Resolved 52 packages`, exit 0 |
| actionlint 1.7.7 on `ci.yml` | yes | the only findings are `runs-on: ubuntu-26.04` being an unknown label to that actionlint version, the same findings as on `main`. shellcheck was not installed, so actionlint did not lint the shell inside the steps |
| The step's script, taken from `ci.yml` by the test's own parser, run with bash against a real image tagged `addon:ci` | yes | prints `the built image runs Python 3.14.8, the version BASE_PYTHON_VERSION names`, exit 0. With a copy of `versions.env` that says `3.14.7` it prints `::error file=infrastructure/docker/versions.env::the built image runs Python 3.14.8, but BASE_PYTHON_VERSION in versions.env is 3.14.7; ...`, exit 1. `docker run --entrypoint python` on the pinned base digest itself also prints `Python 3.14.8` |
| The full lab image build (`docker build -f infrastructure/docker/Dockerfile --build-arg EDITION=lab -t addon:ci .`) | **no** | this session's outbound proxy is not trusted inside a build container, and it refuses plain-HTTP requests, which the runtime stage's `apt-get update` uses (405 from the proxy). The `addon:ci` image above is the Dockerfile's `build` stage (`--target build`), built from a scratch copy of the Dockerfile that only adds the proxy's certificate to that stage. Both stages start from the same pinned digest and Python lives in `/usr/local` from that base, not from apt, so the version it reports is the one the full image runs; the full build and the step itself are proved by CI on the pull request |
| CI on the pull request, CodeQL, CodeRabbit | **no** | run on the pull request |

## Limitations recorded

- The upload route exists (run 2026-10-26, issue 16). There is no MCP server and no trusted-caller session API yet; they
  are later releases (website proposal, section 22).
- The engine 0.1.0 does not read Terraform: a state or plan is accepted and recorded with a fingerprint, and claims about it
  stay `unknown`. Reading it is engine work, upstream first ([App issue 54](https://github.com/saulpatinojr/HCW-CloudCrawler_App/issues/54), `docs/whats-new-upstream.md`).
- The engine's secret-redaction pattern is quadratic on a string of repeated `eyJ`; the lab refuses more than 16 of them in
  one string until the engine fixes its pattern upstream.
- `security/redaction.py` is a thin layer over the engine's module (the old copy had drifted; see
  `docs/whats-new-upstream.md`), plus the ten words only the lab logs.
- `core-update.yml` now has a `CORE_REF v0.1.0` line to compare with the App's latest release. It has not run against a
  newer release (none exists), so the bump path itself is still unexercised; the scheduled run only reports "already at
  v0.1.0".
- When a newer release exists, `core-update.yml` opens the pull request with a GitHub App token (the HCW Main Admin App: its client ID is the repository variable
  `HCW_MAIN_ADMIN_CLIENT_ID`, its private key the repository secret `HCW_MAIN_ADMIN_PRIVATE_KEY`), not `GITHUB_TOKEN`, so the required checks run on the pull request itself. That path is
  covered by `tests/security/test_core_update_app_token.py` (static) and was linted with actionlint and zizmor; it has not
  yet opened a real bump pull request here. To prove the credential without a release to adopt:
  `gh workflow run core-update.yml -R saulpatinojr/HCW-CloudCrawler_AddOn --ref main -f probe=true`.
  The App key lives only as the repository secret `HCW_MAIN_ADMIN_PRIVATE_KEY` and is never printed. To rotate it,
  generate a new private key on the settings page of the App (https://github.com/settings/apps), replace the secret in every repository that holds the key (this one:
  https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/settings/secrets/actions; the App is installed on the four
  add-on repositories, so check the other three), then delete the old key on the settings page of the App.
  The settings page can hold several keys, so a separate key per repository lets you revoke one without
  touching the others.
  **Accepted risk, so nobody has to rediscover it.** A repository secret can be read by any workflow that runs from a branch
  someone with write access can push, so `base-update.yml` is a second reader of the key beside `core-update.yml` (both can
  be started by hand with `workflow_dispatch`), and the base-update proof depends on that: it runs the workflow from a
  throwaway branch. As of 2026-10-27, only the owner can push here. The App is installed on the four add-on repositories, and both
  workflows ask the token action for this repository only (`repositories: ${{ github.repository }}`) with Contents and Pull
  requests write; a token lasts one hour. A modified workflow on another branch could ask for more: the limit is then whatever
  the App was granted when it was installed (that list is on the App's settings page, https://github.com/settings/apps, and is
  not repeated here because a session cannot read it), which is why the key is a risk. The owner decided on 2026-10-26 to leave the key as a repository secret
  ([HCW-HybridCloudWorks#1410](https://github.com/saulpatinojr/HCW-HybridCloudWorks/issues/1410)); the stronger options
  (an environment limited to `main`, or a separate App installation for each repository) can be reopened if the key is ever
  suspected leaked. A separate key for each repository on the same App is not one of them: it helps rotation (one key can be
  revoked without touching the others) but it does not shrink what a stolen key can reach, because every key authenticates the
  same App, and that App is installed on all four add-on repositories. An environment limited to `main` would also stop the
  base-update proof, which needs a run from a branch.
  Auto-merge of a
  compatible bump needs the repository setting "Allow auto-merge" and the variable `CORE_AUTOMERGE=true`; on 2026-10-26 (UTC) neither was set here. "Allow auto-merge" has since been turned on,
  but `CORE_AUTOMERGE` is still not set, so a compatible bump waits for a person to merge it.
- Human verification is wired to the upload route and tested with a stand-in verifier; it has not been exercised against a
  real site key and secret (see the 2026-10-26 run).
- The base-image digest is the website's current pin (moved on 2026-10-26; before that, the Cloud Assessor AddOn's pin of
  2026-10-16), and the uv-image digest is the Cloud Assessor AddOn's verified pin of 2026-10-16; CI
  re-resolves the uv digest on every run and the weekly job compares the base with the website's.
- `base-update.yml` (issue [27](https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/issues/27)) moves the base image pin to the
  website's pin by opening a pull request, with the same HCW Main Admin App credential as `core-update.yml`. It is a port, not a
  new design: its five files (`.github/workflows/base-update.yml`, `scripts/follow_website_base.py`,
  `tests/unit/test_follow_website_base.py`, `tests/unit/test_base_image_pin.py`, `tests/security/test_base_update_workflow.py`)
  were copied byte for byte from the version that was proved live in the Cloud Assessor AddOn on 2026-10-27
  ([the record](https://github.com/saulpatinojr/HCW-CloudAssessor_AddOn/pull/59)). **Verified here:** the copies are
  identical (each file was written from the git blob of the Cloud Assessor file on `main` and `git hash-object --no-filters`
  prints the same blob id for it; a first copy through the contents API's raw download changed one escape sequence in
  `tests/unit/test_follow_website_base.py`, which the blob id caught), and this repository's lint and tests pass with them
  (`ruff check` and `ruff format --check` clean, `uv lock --check` clean, 477 tests passed with 97.59% coverage, 167 of them
  from the three new test files); `core-update.yml`'s probe runs on 2026-10-26 (for example
  [run 40322381612](https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/actions/runs/40322381612)) minted the App token for
  this repository. **Not verified here until this repository's own proof has run** (`docs/operations/runbook.md`, "Keeping the
  base image on the website's pin"): that `base-update` runs at all here (it cannot be started until it is on `main`); the first
  scheduled run (07:37 UTC); that the pull request is pushed and opened with that token here (`core-update.yml` has not opened a
  real pull request in this repository either); what the ruleset option "require extra approval for unattributed changes" does to
  a pull request into `main` (the Cloud Assessor proof's pull requests went into a throwaway branch, so it did not show this);
  and that the runner's own `docker buildx` and `python3` behave here as they did there (same runner label, not looked at
  here). The `ci.yml` `lint` job still checks the pin against every `FROM`, and the weekly `base-follows-website` job still
  compares the image and its digest with the website's. That job does not look at the Python version, so it is not a
  full second check: if the website changes only `BASE_PYTHON_VERSION` to another minor line, `base-update` refuses and
  goes red while the weekly job stays green. Watch for failed `base-update` runs on their own
  (`docs/operations/runbook.md`, "When the run is red").
- The labels in `.github/labels.json` and the repository Discussions were not created (the initializer ran with
  `--skip-github`, having no signed-in `gh` here); the owner runs the template's GitHub step once.
