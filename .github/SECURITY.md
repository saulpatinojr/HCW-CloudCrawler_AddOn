# Security policy

## Reporting a vulnerability

Use GitHub private vulnerability reporting or the private security contact documented in this repository's Security page or README. Do not open a public issue containing exploit details, credentials, tokens, private endpoints, tenant identifiers, personal data, or customer data.

If no private reporting channel is available, open a minimal public issue asking maintainers for a secure contact method without describing the vulnerability. Do not test systems or data you do not own or have explicit authorization to assess.

Include the following in a private report when safe:

- affected version, branch, component, or commit;
- concise impact and preconditions;
- reproduction steps or a minimal proof of concept with sensitive values removed;
- sanitized logs, traces, or screenshots; and
- known mitigation, workaround, or disclosure deadline.

## Scope

Report issues affecting:

- application and library source;
- infrastructure, deployment, build, and configuration;
- CI/CD workflows, actions, release automation, and artifact handling;
- authentication, authorization, tenancy, data handling, and integrations;
- logging, telemetry, error handling, and monitoring; and
- examples, tests, fixtures, generated files, and documentation that can expose secrets or sensitive data.

Known limitations already documented in the repository's risk register do not need to be reported again unless the report identifies a missing control, materially broader impact, or bypass.

## Secret exposure

Treat any secret or sensitive value found in a commit, issue, log, artifact, or documentation as disclosed. Notify maintainers privately, preserve only the minimum evidence needed for investigation, and rotate or revoke the value through the incident process.

## Triage and disclosure

Maintainers will acknowledge and triage reports as soon as practical. Timelines depend on severity, affected versions, maintainer availability, and coordination with users or upstream projects. Keep reports private until maintainers confirm that coordinated disclosure is appropriate.

## Supported versions

| Version or branch | Supported |
| --- | --- |
| `main` | Yes |
| The latest tagged release | Yes |
| Earlier tagged releases | No; upgrade to the latest release |

## Maintainer contact and response target

Report privately through GitHub private vulnerability reporting on this repository (Security tab, "Report a vulnerability"). The maintainer is the repository owner listed in `.github/CODEOWNERS`. Reports are acknowledged as soon as practical; this is a one-maintainer project and no response time is promised.
