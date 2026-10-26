# Samples

Fictional inputs for the upload route and the pane's "Use the sample" buttons. Every file uses subscription
`00000000-0000-0000-0000-000000000001` and `hcw-sample-*` names only (storage accounts, whose names Azure forbids a hyphen
in, are `hcwsamplestprod01` and `hcwsamplestdev01`); nothing here is or ever was a real estate. The lab serves these
four files at `GET /api/samples/<file name>`, from `/app/samples` in the image.

An upload is one JSON object with two parts: the evidence (what is built) and the decision (what you decided). The
pane builds that object for you from the files you pick. By hand, it looks like this (the files named here are in this
folder):

```json
{
  "evidence": [{ "kind": "arg-export", "name": "sample-resource-graph.json", "content": { "...the whole export...": "" } }],
  "decision": { "...the whole decision file...": "" }
}
```

| File | What it is |
| --- | --- |
| `sample-resource-graph.json` | A portal-shaped Azure Resource Graph export (`{count, data}`) of a small estate of 13 resources: two SQL databases (one zone redundant, one not) and their SQL server (public access enabled, no private endpoint), two storage accounts (zone-redundant storage in prod with an approved private endpoint, locally redundant in dev), an App Service plan and a web app in the wrong region with no owner tag and no identity, a PostgreSQL flexible server, a Cosmos DB account with one non-zone-redundant secondary location and no private endpoint, an AKS cluster across three zones, a virtual machine, a zone-redundant public IP and a Key Vault with an approved private endpoint. Use as `kind: "arg-export"`. |
| `decision-starter.json` | A generic starting decision with four claims (no public access on data stores, private endpoints, managed identity, an owner tag) and no region, tag value or subscription, so it applies to any export. Edit it before you rely on it. |
| `decision-zone-redundancy.json` | One claim: production data-platform resources (scoped by the tag `env=prod`) are zone redundant. Against the sample export it contradicts `hcw-sample-sql-01` and `hcw-sample-cosmos-prod-01` and supports three others. |
| `decision-wave-one.json` | Six claims for a production baseline, one per resource detector other than zone redundancy: public access disabled, private endpoint present, managed identity, owner tag, region `centralus`, and a zone-redundant storage SKU. |

The two decision files and the export are the App's own samples (`HCW-CloudCrawler_App`, `samples/`), copied unchanged,
so the same files work in both editions. The tests hold the lab to the App's expected verdicts for them
(`tests/acceptance/`).

## Writing your own decision

A decision file has a `title`, optional text fields (`context`, `decision`, `decisionDrivers`, `consequences`,
`constraints`, `assumptions`, `risks`, `openQuestions`) and between 1 and 20 `claims`. A claim names a detector
(`detectorId`), says what it expects (`expectation`: a `property` name, an `operator` and a `value`), and may narrow
which resources it covers (`selector`: `resourceTypes`, `tagSelectors`, `nameGlobs`, `subscriptionIds`) and take
`parameters` (for example `{"tag": "owner"}` for `tag-required`). The detectors are `zone-redundancy`,
`public-access-disabled`, `private-endpoint-present`, `managed-identity`, `tag-required`, `sku-allowed`,
`region-allowed`, `advisor-findings`, `retirement-exposure` and `policy-assignment-present`; the last three read Azure
results this edition never receives, so they report `unknown`. The limits on lengths and counts are listed in
[`docs/api.md`](../docs/api.md).

## Terraform files

`tf-state` (a version 4 state) and `tf-plan` (the JSON from `terraform show -json`, `format_version` 1.x) are accepted as
evidence, but the engine this edition runs (`cloud-crawler-core` 0.1.0) does not read Terraform yet: it records a
fingerprint and the claims about it stay `unknown`. State files can hold secrets in plain text. The lab keeps nothing of
the content after the answer is built, but strip secrets from a state before you upload it anyway.
