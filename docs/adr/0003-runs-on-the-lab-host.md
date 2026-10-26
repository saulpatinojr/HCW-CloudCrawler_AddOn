# 0003. The lab edition runs on the website's lab host as one hardened container, pinned by digest

- **Status:** Accepted
- **Date:** 2026-10-21
- **Owners:** Workload owner and architecture owner
- **Issue:** none; follows the website's ADR 0035 (AddOn pane model) and the Cloud Assessor AddOn's ADR-0003

## Context

The website operates a lab host (`*.lab.hybridcloudworks.com` behind its reverse proxy, configured by the website
repository's Ansible) with a pane model, a status proxy and a hardening baseline, and runs every AddOn as one
hardened container through its generic `addons` role. The App edition of Cloud Crawler, by contrast, runs on Azure
Container Apps beside an Azure MCP Server container under a managed identity or on-behalf-of authentication; the lab
host can neither offer that nor should.

## Decision

- **Lab edition: the lab host.** One `docker_container` named `hcw-addon-cloud-crawler`, image
  `docker.io/hybridcloudworks/img-cc-lab-addon` by digest, a loopback port assigned in the website's
  `group_vars` when the row is added (the Cloud Assessor uses 18083; the next free port is the website's call),
  hostname `cloud-crawler.lab.hybridcloudworks.com`, environment from `group_vars`, the verification secret from the
  host vault (`vault_addon_cloud_crawler_turnstile_secret`), run with read-only root, `tmpfs /tmp`, `cap_drop ALL`,
  `no-new-privileges`, 512m, 256 pids, one CPU, the image's own `HEALTHCHECK`, no volumes, no socket. This repository
  ships no Terraform for the host and only a local `docker-compose.yml` for development.
- **The trusted-caller path**, when it ships, is reached by the website's Function App over https exactly as
  `/api/health` is today; no new egress from the host and no inbound path other than the reverse proxy.
- **Publishing** is tag-driven (`publish-images.yml`): build, boundary check inside the image, Trivy (HIGH and
  CRITICAL, fixed only), push with provenance, SBOM and attestation through the Docker OIDC connection, gated on the
  repository variables `DOCKERHUB_ENABLED` and `DOCKERHUB_CONNECTION`. The printed digest is what the website pins.

## Alternatives considered

| Alternative | Benefits | Drawbacks | Reason not selected |
| --- | --- | --- | --- |
| Run the lab edition on Container Apps beside the App | One platform | A paid resource for an anonymous lab; the site's pane and status contracts are built for the lab host; an identity endpoint would be present, which the lab refuses by construction | Cost and the boundary |
| Serve the lab from the website's own origin | No new origin | Breaks the site's closed CSP and puts AddOn code into the site bundle, which ADR 0035 rejected | Rejected by the site's own decision |

## Consequences

- The site's coupling to this AddOn is one digest in `group_vars`, one app setting and one `frame-src` entry;
  rollback is the previous digest.
- The lab host's resource ceiling gains one container (512m / 256 pids); the website records it beside its capacity
  assertions.
- Running the lab anywhere that offers an identity endpoint is impossible by construction, so the two editions cannot
  be confused in deployment any more than in code.

## Validation

The website's catalogue row turns `available` only when a published digest exists and the AddOn integration standard's
checklist is worked; `ci.yml` builds the image on every pull request and `publish-images.yml` proves the boundary
inside it before any push.

## Rollback or revisit trigger

Remove the `group_vars` row and the role prunes the container. Revisit if the website retires the lab host or changes
the AddOn pane model.
