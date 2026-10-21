# 0001. The lab edition never calls Azure: evidence is handed in or uploaded, and the engine is adopted from the App

- **Status:** Accepted
- **Date:** 2026-10-21
- **Owners:** Workload owner and architecture owner
- **Issue:** none; recorded from the owner-approved proposal *Azure Architecture MCP Appliance on Azure MCP Server 3.0* (website repository, `docs/architecture/azure-architecture-mcp-appliance.md`, sections 7, 8, 11 and 12)

## Context

Cloud Crawler evaluates Azure environments with Azure MCP Server 3.0 as the source of truth for observations and the
appliance as the source of truth for decisions, claims, evidence, contradictions, reviews and approvals. The program's
lab edition runs on the website's lab host, framed by the site, for anonymous and lightly authenticated visitors. The
existing Cloud Assessor AddOn proved the strongest property the program has: a lab that is technically unable to
construct a cloud credential (no SDK, startup refusal under identity variables, no Azure endpoints in code or pane).

The new design adds a chat path in which a signed-in visitor's Azure observations arrive through Azure MCP under
on-behalf-of authentication. Someone has to call Azure MCP with the visitor's delegated token. Routing that token
through the lab host would put a bearer for Azure Resource Manager scopes on a credential-free VPS, require Azure
egress from the host, and force this application to handle Entra tokens, which the boundary test forbids.

## Decision

1. **This edition collects evidence but never fetches it.** Its inputs are uploads (Resource Graph exports, review
   reports, Terraform artifacts) and results the website hands in through a trusted-caller session API after calling
   Azure MCP itself with the visitor's request-scoped token. The website asserts `{tenantId, userId, sessionId}`;
   this edition validates no Entra token, holds no Azure token and calls no Azure endpoint.
2. **The boundary stays enforced, not documented.** `edition.py` refuses to start under `IDENTITY_ENDPOINT`,
   `MSI_ENDPOINT`, `AZURE_CLIENT_SECRET`, `AZURE_FEDERATED_TOKEN_FILE`, `AZURE_CLIENT_ID` or `AZURE_TENANT_ID`,
   refuses an importable `azure`, `msal` or `boto3`, and installs an import guard. The security suite proves no module
   imports an outbound HTTP client (human verification excepted), no route calls out, no code or pane references
   `management.azure.com`, `login.microsoftonline.com` or `graph.microsoft.com`, and the image cannot import a cloud
   SDK. When the MCP server surface arrives, the suite additionally asserts the tool list carries no tool that calls
   Azure.
3. **The engine is adopted from the App unchanged.** `cloud-crawler-core` is written and versioned in
   `HCW-CloudCrawler_App` (pydantic only, no HTTP, no cloud SDK). This repository pins the wheel the App attaches to
   its GitHub Release, by URL, so `uv lock` records its sha256 and the image's `pip install --require-hashes`
   verifies it; `core-update.yml` opens the bump pull request on each upstream release. Until the first release the
   lab has no engine and accepts no uploads; the pane says so.
4. **Honesty is in the data.** Findings are `supported | contradicted | unknown | not-applicable`; unknown lowers
   coverage, never score; what an upload cannot show stays unknown by design; every bundle ships `NOT-AN-AUDIT.md`.

## Alternatives considered

| Alternative | Benefits | Drawbacks | Reason not selected |
| --- | --- | --- | --- |
| The AddOn relays the visitor's delegated token to Azure MCP itself | One fewer hop; the AddOn "collects" in the fetching sense | A bearer for Azure scopes on the lab host; Azure egress from the host; Entra token handling in the AddOn; every "no cloud connectivity" label weakened; the boundary test suite would have to be loosened | Breaks the one property the program has proven, for one hop |
| The AddOn signs the visitor in itself (its own SPA registration in the pane) | Self-contained | Sign-in moves out of the website, which owns authentication; the pane contract forbids password fields and sign-in; two identity systems | Contradicts the website's responsibilities and the pane standard |
| No chat path in the lab; uploads only | Simplest | The lab could not show Advisor, Pricing, Policy or Cloud Architect evidence, which the design's MVP needs | Too little for the lab story; the handed-in path costs one API and keeps the boundary |

## Consequences

- One extra hop (site to AddOn) for handed-in evidence and one trusted-caller key in the host vault, in exchange for a
  boundary that stays exactly as tested.
- The lab cannot run scheduled collections, persist across sessions or produce evidence only live collectors can
  (locks, diagnostics, spend); those stay `unknown` here and belong to the App's appliance edition.
- Feature promotion is one direction: App, validation, AddOn, website. Anything needing a credential, a store, a
  scheduler, a pipeline runner, elicitation or sampling never enters this repository.

## Validation

Implementation owner: the workload owner. Evidence: `tests/security/test_edition_boundary.py` and
`tests/security/test_no_secrets.py` green on every pull request; `ci.yml` builds the image and proves `import azure`
fails and the container exits under `IDENTITY_ENDPOINT`; `/api/health` reports `azureConnectivity:
disabled-by-design`; `VALIDATION.md` records each run.

## Rollback or revisit trigger

Revisit only if the website stops owning sign-in, or if the program decides the lab host may hold delegated Azure
tokens. Either would be a new ADR superseding this one, with the boundary suite rewritten in the same pull request.
