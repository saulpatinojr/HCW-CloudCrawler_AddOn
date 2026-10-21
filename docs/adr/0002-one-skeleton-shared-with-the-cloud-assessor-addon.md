# 0002. One skeleton shared with the Cloud Assessor AddOn; no shared kit yet

- **Status:** Accepted
- **Date:** 2026-10-21
- **Owners:** Workload owner and architecture owner
- **Issue:** none; follows the Cloud Assessor AddOn's ADR-0002 (shared skeleton convention) and the website's AddOn integration standard

## Context

The program's Python AddOns implement the same HTTP and container contract: the flat `/api/health` envelope, the error
envelope, security headers with configurable `frame-ancestors`, exact-origin CORS, fail-closed human verification,
body, row and item caps, a per-client token bucket behind `<PREFIX>_TRUST_PROXY`, a concurrency bound, content-free
logs, an in-memory TTL store with hashed owner tokens, the `hcw-addon` pane bridge, the two-stage hash-pinned
Dockerfile on the website's base digest and the same workflow set. `HCW-CloudAssessor_AddOn` is the reference; this
repository was created from the same template and must integrate with the site the same way.

## Decision

- This repository copies the Cloud Assessor AddOn's skeleton **module for module** with the package renamed to
  `cloud_crawler_lab` and the settings prefix to `CC_`: `config.py`, `edition.py`, `errors.py`,
  `security/{turnstile,headers,cors,limits,ratelimit,logging,redaction}.py`, `routes/*`, `app.py`
  (`create_app(settings)`), `__main__.py`; `web/{index.html,app.js,styles.css,theme.css}`; the same `tests/` layout;
  `infrastructure/docker/{Dockerfile,versions.env}`; the four workflows.
- `security/redaction.py` is a verbatim copy of the engine's redaction module, carried only until the engine is
  adopted; it is deleted in the adoption pull request.
- **No shared package yet.** A kit would freeze guesses before this edition has run against real traffic. Divergence
  from the Cloud Assessor AddOn is allowed only where the domain differs (evidence kinds, detectors, the MCP server
  surface, the trusted-caller session API); anything in the contract layer that differs between the two is a bug in
  one of them.

## Alternatives considered

| Alternative | Benefits | Drawbacks | Reason not selected |
| --- | --- | --- | --- |
| Extract `hcw-addon-kit` now and depend on it | No duplication | Freezes an API before two consumers have exercised it; a third repository to version | Premature |
| Write a new skeleton for this product | Freedom | Reviewers would have to learn two contract layers; the site integrates both the same way | Duplicated review cost with no benefit |

## Consequences

- Reviewers can read one AddOn and review the other; the website's pane page, status proxy and Ansible role need no
  special case.
- A few hundred lines of duplication until a kit exists; when it is extracted, both AddOns adopt it in the same
  release train and this ADR is superseded.

## Validation

`tests/contract/test_health_shape.py` pins the health and pane contracts; the website's AddOn integration standard
compliance checklist is worked before the catalogue row turns `available`.

## Rollback or revisit trigger

Reopen when a second Python AddOn change has to be applied to both trees by hand twice in one quarter; that is the
signal the kit pays for itself.
