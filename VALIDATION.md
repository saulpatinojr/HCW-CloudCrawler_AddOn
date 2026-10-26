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
  touching the others. Auto-merge of a
  compatible bump needs the repository setting "Allow auto-merge" and the variable `CORE_AUTOMERGE=true`; on 2026-10-26 (UTC) neither was set here. "Allow auto-merge" has since been turned on,
  but `CORE_AUTOMERGE` is still not set, so a compatible bump waits for a person to merge it.
- Human verification is wired to the upload route and tested with a stand-in verifier; it has not been exercised against a
  real site key and secret (see the 2026-10-26 run).
- The base-image digest is the website's current pin (moved on 2026-10-26; before that, the Cloud Assessor AddOn's pin of
  2026-10-16), and the uv-image digest is the Cloud Assessor AddOn's verified pin of 2026-10-16; CI
  re-resolves the uv digest on every run and the weekly job compares the base with the website's.
- The labels in `.github/labels.json` and the repository Discussions were not created (the initializer ran with
  `--skip-github`, having no signed-in `gh` here); the owner runs the template's GitHub step once.
