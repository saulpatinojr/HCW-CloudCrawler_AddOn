# Changelog

All notable changes to this repository are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) where it versions
anything.

Add an entry under **Unreleased** in the same pull request as the change.
Several open pull requests collide on this section, so when two are open at
once, merge one before rebasing the next.

## [Unreleased]

### Added

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
