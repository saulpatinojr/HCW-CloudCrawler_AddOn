# Website integration guide

How `hybridcloudworks.com` shows the Cloud Crawler lab edition, per the HCW AddOn Integration Standard (website
repository `docs/standards/addon-integration-standard.md`, ADR 0035). The site frames this AddOn in a sandboxed pane on
one page; nothing from this repository is installed into the site bundle.

**Where it stands, read on 2026-10-26.** The website's catalogue row for this AddOn is `status: 'available'`
(website pull request [1413](https://github.com/saulpatinojr/HCW-HybridCloudWorks/pull/1413), for website issue 1357): `/tools/cloud-crawler` frames the
tool and the Tools menu lists it, from the day the owner deploys the website (it is deployed by hand). The image is `v0.2.0`
(digest `sha256:5a43c90bda9bed1d3472847f492b7c05405e6a6ce2d4aa7f4d9b519bb72daf28`, issue 17), the first with the upload
route. The lab host has run it on `127.0.0.1:18084` since the owner's playbook run of 2026-10-26, and the website's status
route then answered `configured: true, reachable: true`, version `0.2.0`, edition `lab`. The website's row does not promise
Terraform: the engine this image runs (`cloud-crawler-core` 0.1.0) records a Terraform state or plan but does not read it,
so the row's summary and technology list leave Terraform out until this repository ships an engine that does. Not verified by
any session when this was written: the pane inside the website's frame in a real browser, and one real upload with the human
check (the owner's first checks after the website deploys). The website's page for this pair
(`docs/architecture/app-to-addon/cloud-crawler.md`) holds the rest of the record.

## Identity

| Item | Value |
|---|---|
| AddOn id | `cloud-crawler` |
| Site route | `/tools/cloud-crawler` (`frontend/src/pages/tools/AddOnPanePage.jsx` with `addonId="cloud-crawler"`; `CloudCrawlerPage.jsx` wrapper) |
| Origin | `https://cloud-crawler.lab.hybridcloudworks.com` (exactly `'https://' + id + '.lab.hybridcloudworks.com'`) |
| Frame `src` | `https://cloud-crawler.lab.hybridcloudworks.com/` plus `?theme=dark` or `?theme=light`: the site builds `origin + panePath` and, since website issue #1353 (pull request #1359), adds the visitor's theme (`addonFrameUrl` in the catalogue). The pane reads the parameter (`web/app.js`) and otherwise follows `prefers-color-scheme`. |
| Health path | `/api/health` |
| Function App setting (status proxy) | `ADDON_CLOUD_CRAWLER_URL`. The registry (`functions/src/lib/addons/registry.js`) names it and `infra/functionapp.tf` declares it as a plain setting, applied by the owner's Terraform run; the status route reads this AddOn's `/api/health` through it. |
| Lab-host vault key | `vault_addon_cloud_crawler_turnstile_secret` (ADR 0003 here) |
| Lab-host loopback port | 18084 (the website's call, as ADR 0003 leaves it; the next after the Cloud Assessor's 18083; published on `127.0.0.1` only, behind the host's reverse proxy) |
| Image | `docker.io/hybridcloudworks/img-cc-lab-addon`, published on `v*` tags by `publish-images.yml`. The lab host runs `v0.2.0`, digest `sha256:5a43c90bda9bed1d3472847f492b7c05405e6a6ce2d4aa7f4d9b519bb72daf28`, the first with the upload route (issue 17), pinned in the website's `lab-host/ansible/group_vars/all.yml` `addons[]`. `v0.1.0` (the engine adopted, no upload route) is also published and is not pinned. |

## Catalogue row (`frontend/src/data/addons/catalogue.js`)

The website's row is the authority. This is a copy of it as of 2026-10-26 (website pull request [1413](https://github.com/saulpatinojr/HCW-HybridCloudWorks/pull/1413)). When
this block and the website disagree, the website is right; the other three AddOns' guides had a pasted row that drifted
this way, which is why the source is named. The weekly check in `.github/workflows/guide-drift.yml` compares the twelve
fields below, and the loopback port in the table above, with the website's `main`.

```js
{
  id: 'cloud-crawler',
  title: 'Cloud architecture drift check',
  summary: 'Upload an export of your Azure resources and see where what is built has drifted from your architecture decisions, with draft decision records and review notes. Nothing you upload is kept beyond two hours.',
  origin: 'https://cloud-crawler.lab.hybridcloudworks.com',
  panePath: '/',
  healthPath: '/api/health',
  providers: ['azure'],
  technology: ['resource-graph', 'architecture-decisions'],
  status: 'available',
  capabilities: ['downloads', 'clipboard-write'],
  docsUrl: 'https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn#readme',
  articleSlugs: []
}
```

The row was `coming` from 2026-10-24 and flipped to `available` (with `comingSince` and `comingReason` removed) in the website's
second pull request for issue 1357, once the App had released, this AddOn had published `v0.2.0` and the lab host ran it. The
summary and the technology list leave Terraform out until an engine that reads it ships here; then both are restored in the
website's row and in this copy, in a pair of pull requests, so the weekly check stays green. `title`, `summary` and
`comingReason` (while it existed) obey the site's public-copy rule (no vendor names; "human verification", "expires after two
hours").

## Status proxy

`GET /api/public/addons/cloud-crawler/status` (anonymous, registered in `functions/src/lib/addons/registry.js` with
`setting: 'ADDON_CLOUD_CRAWLER_URL', healthPath: '/api/health'`) reads this AddOn's `/api/health` with a 5 s timeout and
projects exactly `configured, reachable, version, edition, capabilities, asOf`. Every other health field (`siteOrigins`,
`azureConnectivity`, `limits`, the human-verification fields) is for the pane and is never forwarded. Until the setting
exists the route answers `{ configured: false }` with no network call (a website test holds this for this id). Once it
exists, the pane mounts only when the proxy answers `configured: true, reachable: true`; otherwise the page shows "This
tool isn't available right now."

## Pane protocol

The pane posts, to each origin listed in the `siteOrigins` field of the JSON that its own `GET /api/health` returns (that field comes from the env setting `CC_SITE_ORIGINS`; never `*`):

```json
{ "type": "hcw-addon", "id": "cloud-crawler", "state": "ready" }
```

with the states `loading`, `ready`, `working` and `unavailable`, as the README and `CLAUDE.md` of this repository state. The
site accepts a message only when `event.origin === origin`, `event.source === frame.contentWindow`,
`data.type === 'hcw-addon'`, `data.id === 'cloud-crawler'` and `data.state` is one of the four. A page's 30 s watchdog shows
the unavailable sentence if nothing arrives.

## Sandbox and capabilities

Base sandbox `allow-scripts allow-same-origin allow-forms`. The website's row grants `downloads` and `clipboard-write`, and
not `navigate`, following the rule settled in website issue 1354 (pull request 1359): a pane is granted what it uses.

- `downloads` adds `allow-downloads` to the sandbox. The "Download report" buttons save a file made in the browser, and the two
  sample links carry the `download` attribute.
- `clipboard-write` is a Permissions Policy grant to this origin for the "Copy report" button. It is the write-only grant: the
  pane never reads the clipboard, and when the browser refuses the copy the pane falls back to selecting the text.
- `navigate` is not granted because the pane never posts a `navigate` message (it posts only the four states above); the row
  held it before only because it was copied from the first add-on.

Never `allow-top-navigation`.

## What `/api/health` reports as capabilities

The status proxy projects the `capabilities` list from health. The lab's list as of `0.2.0` (only ever added to) is `health`, `pane`,
`upload-evidence`, `drift-findings`, `draft-decision-record`, `review-proposals`, `report-markdown`, `report-json`,
`not-an-audit`, `sample-data` and `delete-now`. These are the lab's own names and are different from the sandbox
capabilities of the row above. The MCP server surface and the trusted-caller session API are later releases and are not
in the list.

## Content security policy, both sides

- Site: `frame-src` lists `https://cloud-crawler.lab.hybridcloudworks.com` (derived from `addonOrigins()`) now that the row is
  `available`, and the origin is also in the site's `Permissions-Policy` lists for `clipboard-read`, `clipboard-write` and
  `fullscreen`, as for the other three AddOns. That header is a ceiling: what the frame is actually given is decided by the
  row's `capabilities`, which here is `clipboard-write` only. The origin had no entry while the row was `coming`.
- AddOn: `frame-ancestors` from `CC_FRAME_ANCESTORS` (default `'none'`, which is what a direct visit sees), set by the lab
  host to the host's `caddy_frame_ancestors`: `'self'` and the two site origins. Both policies are enforced by the browser;
  they must agree.

## Environment (rendered by the website's `addons` role from its `cloud-crawler` row)

The settings are the `.env.example` of this repository. The last column is what the website's `cloud-crawler` row in
`lab-host/ansible/group_vars/all.yml` sets.

| Variable | Store | Expected on the lab host |
|---|---|---|
| `PORT` | `addons[].env` | `8080` |
| `CC_FRAME_ANCESTORS` | `addons[].env` | `'self' https://hybridcloudworks.com https://www.hybridcloudworks.com` (the host's `caddy_frame_ancestors`) |
| `CC_SITE_ORIGINS` | `addons[].env` | `https://hybridcloudworks.com https://www.hybridcloudworks.com` |
| `CC_ALLOWED_ORIGINS` | `addons[].env` | empty (the pane is same-origin with its API) |
| `CC_TRUST_PROXY` | `addons[].env` | `1` (the host's reverse proxy sets `X-Forwarded-For`) |
| `CC_TURNSTILE_SITE_KEY` | `addons[].env` | the widget's public site key, `0x4AAAAAAFmYfaPCx8djlDfP` |
| `TURNSTILE_SECRET` | vault | `vault_addon_cloud_crawler_turnstile_secret` (`secret_env`) |
| `CC_ALLOW_NO_TURNSTILE` | never set on the host | absent (fail closed) |
| `CC_TTL_MINUTES`, `CC_MAX_ITEMS`, `CC_RATE_LIMIT_POSTS`, `CC_RATE_LIMIT_WINDOW_MINUTES`, `CC_MAX_CONCURRENT`, `CC_MAX_STORE_MB` | `addons[].env` | `120`, `200`, `10`, `10`, `2`, `64` |

## What this AddOn calls on the website's backend

Nothing today, and by design nothing that reaches Azure (`docs/adr/0003-runs-on-the-lab-host.md`; the edition boundary).
The upload route's one outbound request is the human-verification check, sent from the lab host to the verification
service with the site key's secret; it is not a call to the website or to a cloud.
The one planned path is the trusted-caller session API for the site's chat experience, which the website's Function App
would reach over https exactly as `/api/health` is reached; it is not built, and no new egress from the host or inbound
path other than the reverse proxy is part of the plan.

## Copy rules for anything a visitor reads

No vendor or tool names on either side of the frame: not the host, the edge, the human-verification provider, the
workspace platform. Say "human verification" and "expires after two hours". Status is shown in words, never by colour
alone.

## Acceptance tests on the website side

Catalogue row validity and registry parity (`catalogue.test.js`), the status route answering `{ configured: false }` for
this id while its setting is unset (`status.test.js`), CSP parity (`csp.test.js`, which holds `frame-src` to the
`available` rows only), route completeness, and public copy.
