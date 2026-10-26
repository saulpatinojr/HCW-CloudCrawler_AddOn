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

## Limitations recorded

- No uploads, no MCP server and no trusted-caller session API yet: the pane shell says so and the file picker is
  disabled. The engine is adopted (run 2026-10-26 below) but nothing calls its ingest or drift code yet; they arrive
  with the following pull requests (website proposal, section 22).
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
  generate a new private key on the settings page of the App (https://github.com/settings/apps), replace the secret
  on this repository's secrets page
  (https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/settings/secrets/actions), then delete the old key on the
  settings page of the App. Auto-merge of a
  compatible bump needs the repository setting "Allow auto-merge" and the variable `CORE_AUTOMERGE=true`; on 2026-10-26 (UTC) neither was set here. "Allow auto-merge" has since been turned on,
  but `CORE_AUTOMERGE` is still not set, so a compatible bump waits for a person to merge it.
- Human verification is configured but unused until an upload route exists; `/api/health` already reports
  `turnstile.required` so the pane's wording is right from the first deployment.
- The base-image digest is the website's current pin (moved on 2026-10-26; before that, the Cloud Assessor AddOn's pin of
  2026-10-16), and the uv-image digest is the Cloud Assessor AddOn's verified pin of 2026-10-16; CI
  re-resolves the uv digest on every run and the weekly job compares the base with the website's.
- The labels in `.github/labels.json` and the repository Discussions were not created (the initializer ran with
  `--skip-github`, having no signed-in `gh` here); the owner runs the template's GitHub step once.
