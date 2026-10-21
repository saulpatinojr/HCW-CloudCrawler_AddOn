# Architecture decision records

One file per decision, numbered in order: `NNNN-short-title.md`, starting at
`0001`. Copy `template.md`. A decision that replaces an earlier one sets the
earlier record's status to **Superseded by NNNN** rather than editing its
content.

Propose a decision with the **Architecture decision record** issue form; once
accepted, record it here and link the issue.

This edition's own decisions. Upstream decisions (the App's) are cited by
number where they apply; the design both editions implement is the website
repository's proposal *Azure Architecture MCP Appliance on Azure MCP Server
3.0* (`docs/architecture/azure-architecture-mcp-appliance.md` there).

| ADR | Title |
| --- | --- |
| [0001](0001-lab-edition-never-calls-azure.md) | The lab edition never calls Azure: evidence is handed in or uploaded, and the engine is adopted from the App |
| [0002](0002-one-skeleton-shared-with-the-cloud-assessor-addon.md) | One skeleton shared with the Cloud Assessor AddOn; no shared kit yet |
| [0003](0003-runs-on-the-lab-host.md) | The lab edition runs on the website's lab host as one hardened container, pinned by digest |

Next number: 0004.
