# CLAUDE.md — working agreement for Claude Code in this repository

This is `saulpatinojr/HCW-CloudCrawler_AddOn`, the **lab edition** of Cloud Crawler (AddOn id `cloud-crawler`, site
route `/tools/cloud-crawler`, origin `https://cloud-crawler.lab.hybridcloudworks.com`): a Python 3.14 FastAPI
application (`src/cloud_crawler_lab`) that collects evidence handed to it, runs the engine's deterministic drift
detectors and expires everything after two hours; a vanilla pane the website frames; a hardened Dockerfile and
SHA-pinned workflows. The engine (`cloud-crawler-core`) is **written upstream** in `saulpatinojr/HCW-CloudCrawler_App`
and adopted here unchanged as a release wheel (ADR 0001; `core-update.yml` opens the bump pull request). Detector and
tool changes go upstream first; this repository owns the lab application, its boundary, its pane and its deployment.
**Read `docs/whats-new-upstream.md` before changing behaviour here, and update it when you adopt an upstream change.**

- Run `uv sync --all-packages`, then `uv run ruff check . && uv run ruff format --check .` and
  `uv run pytest -q --cov=src --cov-fail-under=85` before claiming anything works. Never claim a check passed that
  you did not run; record what ran and what did not in `VALIDATION.md`.
- Never weaken: the lab's inability to construct an Azure credential (no cloud SDK; `edition.py` refuses to start
  under `IDENTITY_ENDPOINT`/`MSI_ENDPOINT`/`AZURE_CLIENT_SECRET`/`AZURE_FEDERATED_TOKEN_FILE`/`AZURE_CLIENT_ID`/
  `AZURE_TENANT_ID`; `tests/security/test_edition_boundary.py`, which also proves no route and no module reaches
  out); fail-closed human verification (uploads answer 503 without a secret unless `CC_ALLOW_NO_TURNSTILE=1`, local
  only); owner-token isolation (hashed, constant-time, 404 for foreign ids); the 5 MB / 5,000-row / 200-item /
  120-minute limits; exact-origin CORS; the content-free log writer; the "not production" and "no cloud connectivity
  by design" labels; the `NOT-AN-AUDIT.md` in every bundle.
- The AddOn **collects evidence but never fetches it**: uploads, or results the website hands in through the
  trusted-caller session API, are the only inputs. No Azure token, access token or refresh token is ever held here;
  the site validates identity and forwards nothing but asserted `{tenantId, userId, sessionId}` claims (ADR 0001).
- Verdicts come from detectors, never from a model: `supported | contradicted | unknown | not-applicable`; unknown
  lowers coverage, never score. Detector ids and evaluator kinds are only added, never renamed.
- No secrets, tokens, customer inventories or real tenant/subscription ids anywhere, fixtures and tests included.
  Samples use subscription `00000000-0000-0000-0000-000000000001` and `hcw-sample-*` names only; every GUID in the
  tree is a placeholder of the form `00000000-0000-0000-0000-0000000000NN` (`tests/security/test_no_secrets.py`).
- No vendor names in anything a visitor can read (not the host, edge, verification provider or workspace platform):
  say "human verification" and "expires after two hours".
- Owner-pasteable commands: no placeholders; bash and PowerShell both acceptable; say which shell.
- `/api/health` is flat (`id`, `version` at the top level); the pane posts `{type:'hcw-addon', id, state}` with states
  `loading | ready | working | unavailable` to each origin in `siteOrigins` only. Every `/api/*` error uses the
  `{error:{code,message,details?}}` envelope.
- Settings carry the `CC_` prefix (`config.py`); the secret is `TURNSTILE_SECRET`, read once and never echoed.
- ADRs: this edition's own in `docs/adr/` (template there; next number: 0005); upstream decisions are cited, not
  copied (the App has published ADRs 0001 to 0003; links are in `docs/whats-new-upstream.md`). Keep `CHANGELOG.md`
  current in the same pull request as the change. Pull requests open ready for review and follow
  `.github/PULL_REQUEST_TEMPLATE.md`.

## How to communicate with the owner

The owner is not a specialist in every tool used here. Write for a junior administrator with limited experience and no
memory of earlier sessions.

- **Be conversational and human.** Plain, friendly sentences. Say what happened and why it matters before the detail.
- **Assume little context.** Do not rely on repository history, ticket numbers or earlier chat. Restate what a thing is
  the first time it appears.
- **Avoid jargon.** When a technical term is unavoidable, explain it in a few words the first time, for example
  "a lockfile (the file that records the exact versions installed)".
- **When the owner must act, give numbered steps.** One action per step, short, saying where to click or what to run and
  which shell (bash or PowerShell). Say what they should see when it worked.
- **When you ask the owner a question, make it answerable.** Say what is being decided and why it matters, list the
  options in plain words with what each one means, give a recommendation, and say exactly how to answer (a word to reply
  with, or the steps and the link for where to click). Never ask a bare "A, B or C?" or "OK to proceed?".
- **When the owner has to fill in a form or a setting, give every non-secret value.** For each field, say the exact text
  to type or paste (name, description, URL), which boxes to tick or leave empty, and where to find it. Always supply a
  description wherever a form has a description field. Never put a password, token, client secret, certificate or private
  key in chat, pull requests, issues or documentation; tell the owner to enter each secret only in the approved secure
  settings field, or through a script that reads it from a file.
- **Include links.** Point to the exact settings page, the issue or pull request, and the official documentation
  (Microsoft Learn, GitHub Docs and similar) whenever one exists.
- **Be honest about status.** Separate what was checked, what is assumed, and what is blocked. Never present a guess as a result.

This applies to chat replies, pull request and issue text, and documentation. It does not apply to code comments or
machine-readable files, which keep following the surrounding style.
