# Changelog

All notable changes to this repository are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) where it versions
anything.

Add an entry under **Unreleased** in the same pull request as the change.
Several open pull requests collide on this section, so when two are open at
once, merge one before rebasing the next.

## [Unreleased]

### Changed

- The lab image states its open-source licence in the form registries and scanners read.
  `infrastructure/docker/Dockerfile` sets `org.opencontainers.image.licenses="MIT"` on the final stage (the SPDX id
  of `LICENSE`, the MIT License). The `image` job in `ci.yml` fails when the built image lacks the label or `LICENSE`
  stops being MIT, and the pre-publish check in `publish-images.yml` fails when the image about to be pushed lacks it.
  The `labels:` input of `publish-images.yml` must not set this label: it would override the Dockerfile's. The image
  tags on Docker Hub on 2026-10-26 (`v0.1.0` and `v0.1.0-rc.1`) were built without the
  label and are not changed; the label reaches Docker Hub with the next tagged release.
- `core-update.yml` opens its bump pull request with a short-lived GitHub App token (`actions/create-github-app-token`, pinned to v3.3.0; the HCW Portfolio Admin App, whose client ID and private key are the `APP_CLIENT_ID` variable and `APP_PRIVATE_KEY` secret of the `admin-ops` environment) instead of `GITHUB_TOKEN`, and the job runs in that environment. Why: a pull request opened with `GITHUB_TOKEN` starts no workflow, so the required checks of the `Protect main` ruleset would never run on it and it could not merge. The token is minted for this repository only, with Contents and Pull requests write, after the compatibility check and just before the pull request is opened; `GITHUB_TOKEN` is now `contents: read` only. Because the App's pull request starts this edition's own CI, the "do not trigger other workflows" comment is gone; the compatibility check in the run still decides the label and whether auto-merge is requested. Turning on auto-merge no longer fails the run when the repository setting "Allow auto-merge" is off (it is off here); it warns and leaves the pull request to merge by hand. A manual run with `probe=true` mints the token and makes one read-only API call, to prove the credential while the pin is already at the latest release and no pull request would open. `tests/security/test_core_update_app_token.py` pins all of it (no `GITHUB_TOKEN` passed to `create-pull-request`, the token step first, the `admin-ops` environment, the two permissions, SHA pins).

## [0.1.0] - 2026-10-26

The first release that is not a release candidate. It is the lab application skeleton with the engine
(`cloud-crawler-core` 0.1.0) adopted from the App; it has no upload route yet (issue
[16](https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/issues/16)), so the pane's file picker is still disabled.
The version stays `0.1.0` on purpose: `0.1.0-rc.1` sorts before `0.1.0` in Semantic Versioning, nothing was ever
released as `0.1.0`, and the tag, `pyproject.toml`, `__version__` and `/api/health` already agree on that number. A
higher number would claim features that are not here, and a pushed `v*` tag can never be moved or deleted. Publishing
the image is the tag `v0.1.0` (tracking issue [17](https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/issues/17)).

- `publish-images.yml` only pushes when it runs on a `v*` tag. A manual run (`workflow_dispatch`) used to reach the push
  step as soon as `DOCKERHUB_ENABLED` was `true`, and then fail at the registry login, because the Docker connection
  trusts tags only. A manual run now builds the image, proves the edition boundary inside it and scans it, then skips
  the push with a notice. That makes a manual run a real dry run.
- The base image digest follows the website's current pin again (`python:3.14.8-slim-trixie@sha256:fbecd461...`, same tag, newer build; `versions.env` and both `FROM` lines). The website rebuilt on it on 2026-10-21; `security.yml`'s `base-follows-website` job, which runs on `main` only, had been red on `main` since at least 2026-10-25 because of it. The first real image is built on the current base.
- The engine is adopted: `cloud-crawler-core` 0.1.0, the wheel attached to the App's release `v0.1.0` (2026-10-26), is now a dependency. `pyproject.toml` pins it by release-asset URL on the one `# CORE_REF v0.1.0` line that `core-update.yml` rewrites, and `uv.lock` records the wheel's sha256 (`25a7abfcec50b0f85cb427145a1fd7fb57898bd09cfc3483edad8a042e5e7be3`, the hash of a fresh download, equal to GitHub's digest for the asset; the wheel's build provenance verifies with `gh attestation verify`). The image build's `pip install --require-hashes` verifies it like every other file. `core-update.yml` is no longer inert: it now compares that line with the App's latest release.
- `[tool.hatch.metadata] allow-direct-references = true` in `pyproject.toml`. The build tool refuses a dependency written as a URL without it, which the plan for the first adoption did not mention. It affects only this project's own wheel, which is never published.
- `security/redaction.py` is no longer a copy of the engine's module. The copy had drifted (the engine's list of words allowed in logs does not contain ten words only the lab logs). It now re-exports the engine's `scrub`, `VisitorDataError` and log guard and adds those ten words (`LAB_ONLY_WORDS`); the guard still runs the engine's own check on everything else. The engine also redacts more than the copy did (shared access keys and private-key headers).
- `security.yml`: the `pip-audit` job leaves the engine out of the list it audits (`uv export --no-emit-package cloud-crawler-core`). The engine is first-party and not on PyPI, so `pip-audit --strict` failed with "Dependency not found on PyPI" on the first adoption pull request. Everything else in the image's runtime set is still audited with `--strict`, and the engine is still installed from the App release with its hash checked.
- `tests/security/test_engine_adoption.py` (new): the pin line has the shape the update workflow rewrites, the installed engine is the pinned version, the lock holds the wheel URL and a sha256, the engine's installed source imports no cloud SDK and nothing that opens a connection, it depends on pydantic only, and the lab's extra log words never overlap the engine's list.
- `docs/whats-new-upstream.md`, `README.md`, `VALIDATION.md`, ADR 0001 and `samples/README.md` say the engine is adopted and what is still not built (the upload route, the MCP server and the trusted-caller session API). `CAPABILITIES` is unchanged (`health`, `pane`): it lists only what exists.
- The lab image repository on Docker Hub is renamed from `hybridcloudworks/hcw-addon-cloud-crawler` to `hybridcloudworks/img-cc-lab-addon` (owner naming convention `img-<short name>-<job>-<type>`, 2026-10-25), and its tag is now the full release tag (`v0.1.0`, not `0.1.0`). `publish-images.yml` (`IMAGE`, the tag, the image title label), the local `:dev` build tag, the README and the deployment and integration documents follow. The container name on the lab host (`hcw-addon-cloud-crawler`) is **not** changed: the website's host role owns it. Nothing is published by this change; the next `v*` tag pushes to the new name once the Docker OIDC connection allows it (the header comment of `.github/workflows/publish-images.yml` lists the two repository variables).
- Hardening: the last step of `publish-images.yml` printed the release version straight into a shell command (`echo "image_tag: ${{ steps.version.outputs.version }}"`). The version comes from the pushed tag's name, so a crafted tag name could inject a command. It now reaches the shell through the environment variable `IMAGE_TAG` and is printed as `"${IMAGE_TAG}"`. This was already present before the rename; only people with write access can push tags.

### Added
- `.github/workflows/guide-drift.yml` switches on the website's check that this repository's integration guide still says what the website says (website issue saulpatinojr/HCW-HybridCloudWorks#1356). It calls a reusable workflow (a workflow that another repository can call, like a function) from the website repository, pinned to a full commit, and compares the catalogue row pasted into `docs/website-integration/integration-guide.md` with the website's row for `cloud-crawler`, field by field. It runs on pull requests that touch the guide or this workflow, every Monday at 06:35 UTC and on demand. It holds no secret and has `contents: read` only. To switch it off, delete the file. How to read a failure: https://github.com/saulpatinojr/HCW-HybridCloudWorks/blob/main/docs/runbooks/addon-guide-drift.md
- `docs/whats-new-upstream.md`: two new entries (App pull requests 33 and 34) and a refreshed "Current upstream state". Neither reaches this repository's code: the App's Microsoft Entra sign-in is in its own host, and its engine is unchanged since commit `4ba5add`. Written because the App's `CLAUDE.md` asks that a tool-schema change (`actorId` now optional in three App tools) is recorded here in the same change set.

- `docs/website-integration/` (`integration-guide.md`, `routes.md`): how the website shows this AddOn, written from this
  repository's README, ADR 0003 and `.env.example` and from the website's real catalogue row. The other three AddOns have
  such a guide; this one did not, and the website had no row for it at all until website pull request #1351 (merge commit
  `e4e53807`, 2026-10-24) introduced Cloud Crawler as a `coming` row. The guide says what exists on each side today (the row,
  the registry entry, the route and the explainer page; no `group_vars` row, no port, no setting, no frame-src entry, no
  image), what flipping the row takes, and which questions are open (the pane's capabilities, website issue #1354; whether
  the site passes its theme, #1353). The row in it is a copy of the website's, injected by a script that then compared
  every one of its 14 fields with the website's file: 0 differ. It names its source commit because pasted rows in the
  other AddOns' guides had drifted.

- `.github/dependabot.yml` groups `pydantic` and `pydantic-core` so they arrive in one pull request. pydantic requires one exact `pydantic-core`, so a `pydantic-core` bump on its own cannot resolve; the same failure closed the App repository's Dependabot pull requests.

- `docs/whats-new-upstream.md`: the memory file about the upstream App (`HCW-CloudCrawler_App`): its current state (no tag and no release yet), what
  changed there and whether it reaches this repository, the steps of the first engine adoption (the first `CORE_REF` line is added by hand), the App's
  decisions, and the open App tickets that matter here. `CLAUDE.md` points to it.
- `CLAUDE.md`: the owner-communication section (plain language, numbered steps, answerable questions, exact values with descriptions, no secrets in chat,
  links, honest status) that the App and its sibling repositories carry.

### Changed

- README: the engine move is ADR 0002 in the App (it said ADR 0001), and it says that the App has not released yet.
- `VALIDATION.md` records that `core-update.yml` stays inert until the first `CORE_REF` line is added by hand.
- `CLAUDE.md`: the App has now published its own ADRs (0001 to 0003), so the ADR rule says they are cited from `docs/whats-new-upstream.md`.

- Repository created from the template and initialised for the Python stack
  (CodeOwners, Dependabot for GitHub Actions and uv, CodeQL for Python and
  Actions, Qlty with ruff and bandit); MIT license; `SECURITY.md` support
  policy and private reporting channel filled in.
- The lab application skeleton `src/cloud_crawler_lab` (0.1.0): settings
  with the `CC_` prefix and bounded numeric values; the edition boundary
  (`edition.py`: refusal under identity and credential variables, refusal of
  an importable cloud SDK, an import guard; `python -m cloud_crawler_lab`
  exits 3 with one scrubbed line); the error envelope; exact-origin CORS;
  security headers with configurable `frame-ancestors`; the body cap, the
  token bucket and the concurrency bound; the human-verification client
  (action `cloud-crawler-upload`); the content-free log writer with its
  redaction guard (a copy of the engine's module until the engine is
  adopted); a flat `GET /api/health` with `id`, `version`, `edition`,
  `capabilities`, `asOf`, `siteOrigins`, `turnstile`, `azureConnectivity` and
  `limits`; a catch-all `/api/*` answering 404 or 405 in the envelope; the
  pane served from `web/` with path containment.
- The pane shell (`web/`): posts `{type:'hcw-addon', id:'cloud-crawler',
  state}` to the published site origins only, honours `?theme=dark|light`,
  carries the "Not production" and "no cloud connectivity by design" labels,
  and explains that uploads open with the App's first release; the file
  picker is present and disabled.
- Tests: unit (config, edition, API, security modules), security (edition
  boundary including a fresh-process refusal and an AST walk for outbound
  imports; no secrets and no non-placeholder GUIDs; content-free logs; no
  vendor names in visitor-facing text) and contract (health shape, version,
  pane protocol); 85 percent coverage gate.
- The hardened lab image (`infrastructure/docker/Dockerfile`: two stages on
  the website's base digest, `uv export --frozen` into `pip
  --require-hashes`, no pip at runtime, uid 10001, `HEALTHCHECK`), its
  `versions.env`, a hardened local `docker-compose.yml`, and the workflows
  `ci.yml` (lint, lock and digest checks, image build with the boundary
  proved inside it, tests), `security.yml` (gitleaks, pip-audit, weekly
  base-pin check), `publish-images.yml` (tag-driven, Trivy, provenance, SBOM,
  attestation, gated on `DOCKERHUB_ENABLED`) and `core-update.yml` (adopts
  `cloud-crawler-core` releases from `HCW-CloudCrawler_App`; inert until the
  first one).
- `CLAUDE.md`, ADRs 0001 (the lab edition never calls Azure; the engine is
  adopted from the App), 0002 (one skeleton shared with the Cloud Assessor
  AddOn) and 0003 (runs on the lab host by digest), `VALIDATION.md`,
  `.env.example`, `samples/README.md`, `infrastructure/README.md`.

### Changed

### Fixed

### Security
