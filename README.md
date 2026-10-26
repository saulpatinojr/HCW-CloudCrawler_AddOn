# HCW Cloud Crawler, AddOn (lab edition)

[![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

The lab edition of Cloud Crawler, Hybrid Cloud Works' Azure architecture
appliance. It is the only Cloud Crawler edition that hybridcloudworks.com
integrates with: the site frames it as a sandboxed pane at
`/tools/cloud-crawler` and, in the lab chat path, hands it evidence through
the site's own API. It exists for demonstrations, labs, training and
evaluation scenarios.

The AddOn **collects evidence but never fetches it**. A visitor uploads an
Azure Resource Graph export, an azqr report or Terraform artifacts, or the
site hands in results it obtained from Azure MCP Server on the visitor's
behalf; the AddOn validates, hashes, redacts and normalises what it is given,
runs deterministic drift detectors against the decision records in the
session, and answers with evidence, drift findings, draft ADRs and review
proposals. Everything lives in memory and expires after two hours.

The engine is not written here. It is
[`cloud-crawler-core`](https://github.com/saulpatinojr/HCW-CloudCrawler_App),
seeded and versioned in the upstream App repository and adopted here
**unchanged** when the App releases (ADR 0002 in the App and ADR 0001 here; the update
workflow in `.github/workflows/core-update.yml` opens the bump pull request).
The engine is adopted at the App's release `v0.1.0` (the wheel's URL is pinned in
`pyproject.toml` and its sha256 is recorded in `uv.lock`); what has changed upstream, and what the
first adoption involved, is in
[`docs/whats-new-upstream.md`](docs/whats-new-upstream.md).
This repository owns only the lab application, its edition boundary, its
pane, its limits and its deployment on the website's lab host.

## No cloud connectivity by design

This edition is technically unable to reach Azure. It is not a configuration
choice; it is enforced and tested:

- no cloud SDK is installed, and the application refuses to start if `azure`,
  `msal` or `boto3` can be imported;
- it refuses to start under `IDENTITY_ENDPOINT`, `MSI_ENDPOINT`,
  `AZURE_CLIENT_SECRET`, `AZURE_FEDERATED_TOKEN_FILE`, `AZURE_CLIENT_ID` or
  `AZURE_TENANT_ID`;
- no code and no pane references `management.azure.com`,
  `login.microsoftonline.com` or `graph.microsoft.com`;
- the pane has no sign-in and no password field; its only input is a file
  picker;
- its MCP tool list contains no tool that calls Azure, and the security suite
  reads the list over the protocol to prove it;
- `/api/health` reports `azureConnectivity: "disabled-by-design"`.

The user's delegated Azure access, when there is one, stays in the website:
the site forwards the visitor's token to Azure MCP Server per request and
hands the **result** to this AddOn as evidence. No Azure credential, access
token or refresh token is ever held here (website proposal section 11).

## Status

Version 0.1.0, the first release: the lab application skeleton with the engine adopted. What exists today:

- the lab application skeleton: configuration, the edition boundary and its
  startup refusal, content-free logging, security headers, exact-origin CORS,
  the upload and rate limits, and a flat `/api/health`;
- the pane shell that posts `{type:'hcw-addon', id:'cloud-crawler', state}`
  with the states `loading | ready | working | unavailable` to the website
  origins only;
- the engine `cloud-crawler-core` 0.1.0 as a hash-pinned dependency, used so far by the log guard only;
- the security suite that proves the boundary, including inside the image;
- the hardened Dockerfile and the publish, security and core-update workflows.

The engine `cloud-crawler-core` 0.1.0 is a dependency and the log guard
uses its rules. Not yet: the upload route ([issue 16](https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/issues/16);
so the file picker is still disabled), the MCP server surface, the trusted-caller session API for the
site's chat path. The roadmap is section 22 of the website proposal
*Azure Architecture MCP Appliance on Azure MCP Server 3.0*; nothing here is
production.

## Getting started

Prerequisites: Python 3.14 (managed by `uv`), `uv` 0.11.

```bash
uv sync --all-packages
uv run ruff check . && uv run ruff format --check .
uv run pytest -q --cov=src
```

Run it locally. Uploads answer `503` until human verification is configured;
the local-only switch below disables that requirement and must never be set
on the lab host:

```bash
CC_ALLOW_NO_TURNSTILE=1 uv run python -m cloud_crawler_lab
```

Then open `http://127.0.0.1:8080/`. The image is
`docker.io/hybridcloudworks/img-cc-lab-addon`, built from
`infrastructure/docker/Dockerfile`; the website pins it by digest and the
lab host runs it behind the site's reverse proxy at
`https://cloud-crawler.lab.hybridcloudworks.com`.

## Integration with the website

| Contract | Value |
| --- | --- |
| Catalogue id | `cloud-crawler` |
| Site route | `/tools/cloud-crawler` |
| Origin | `https://cloud-crawler.lab.hybridcloudworks.com` |
| Health | `GET /api/health`, flat: `id`, `version`, `edition`, `capabilities`, `asOf`, `siteOrigins`, `azureConnectivity`, `limits` |
| Pane message | `{type:'hcw-addon', id:'cloud-crawler', state}` posted to each origin in `siteOrigins` only; states `loading`, `ready`, `working`, `unavailable` |
| Status proxy | the site's `GET /api/public/addons/cloud-crawler/status` reads six fields from health |
| Limits | 5 MB upload, 5,000 rows, 200 items held, 120-minute expiry |

The contract is the website's AddOn integration standard and ADR 0035; this
repository follows it rather than defining it. What exists on each side today,
and what flipping the website's row to `available` takes, is in
[`docs/website-integration/`](docs/website-integration/integration-guide.md).

## Rules that do not bend

- Never weaken the boundary above, the fail-closed human verification, the
  owner-token isolation (hashed, constant-time, 404 for foreign ids), the
  limits, the exact-origin CORS, the content-free log writer, or the "not
  production" and "no cloud connectivity by design" labels. Every output
  bundle carries `NOT-AN-AUDIT.md`.
- No vendor names in anything a visitor can read: say "human verification"
  and "expires after two hours".
- No secrets, tokens, customer inventories or real tenant, subscription or
  resource identifiers anywhere. Samples use subscription
  `00000000-0000-0000-0000-000000000001` and `hcw-sample-*` names only.
- The engine is adopted from the App unchanged. Detector and tool changes go
  upstream first.

## Repository standards

This repository was created from the organisation's template repository. It
carries `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md`,
`.github/SECURITY.md`, `.github/CODEOWNERS`, the pull request and issue
templates, CodeQL, dependency review, Dependabot, CodeRabbit and Qlty
configuration, and `docs/adr/`. Pull requests open ready for review and follow
`.github/PULL_REQUEST_TEMPLATE.md`; `CHANGELOG.md` is updated in the same pull
request as the change.

## Contributing, security, license

See `CONTRIBUTING.md`, `.github/SECURITY.md` and [LICENSE](LICENSE) (MIT).
