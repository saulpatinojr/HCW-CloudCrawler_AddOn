# Website integration guide

How `hybridcloudworks.com` shows the Cloud Crawler lab edition, per the HCW AddOn Integration Standard (website
repository `docs/standards/addon-integration-standard.md`, ADR 0035). The site frames this AddOn in a sandboxed pane on
one page; nothing from this repository is installed into the site bundle.

**Where it stands, read on 2026-10-26.** The website has a catalogue row for this AddOn with `status: 'coming'`, added by
website pull request #1351 (merge commit `e4e53807`): `/tools/cloud-crawler` shows an explainer and frames nothing. That
is deliberate. The App has released `v0.1.0` and this repository has adopted the engine from it. The upload route (issue
16) is built on `main` and is the content of the next release, `0.2.0`; no first real image is published yet (issue 17,
tag `v0.1.0`; only the test image `v0.1.0-rc.1` exists). The website's row should flip to `available` only once an image
that contains the upload route (`v0.2.0`) is published, because the row promises what the route does. Everything below that needs an image (the lab-host row, the port, the Function App setting, the
frame-src entry) does not exist on the website yet. The checklist for the pull request that flips the row is on issue 17,
and the website's page for this pair (`docs/architecture/app-to-addon/cloud-crawler.md`) lists what the flip takes.

## Identity

| Item | Value |
|---|---|
| AddOn id | `cloud-crawler` |
| Site route | `/tools/cloud-crawler` (`frontend/src/pages/tools/AddOnPanePage.jsx` with `addonId="cloud-crawler"`; `CloudCrawlerPage.jsx` wrapper) |
| Origin | `https://cloud-crawler.lab.hybridcloudworks.com` (exactly `'https://' + id + '.lab.hybridcloudworks.com'`) |
| Frame `src` | `https://cloud-crawler.lab.hybridcloudworks.com/` plus `?theme=dark` or `?theme=light`: the site builds `origin + panePath` and, since website issue #1353 (pull request #1359), adds the visitor's theme (`addonFrameUrl` in the catalogue). The pane reads the parameter (`web/app.js`) and otherwise follows `prefers-color-scheme`. |
| Health path | `/api/health` |
| Function App setting (status proxy) | `ADDON_CLOUD_CRAWLER_URL`. The registry (`functions/src/lib/addons/registry.js`) already names it; the website does not declare it in `infra/functionapp.tf` until the row is `available`, so the status route answers `{ configured: false }`. |
| Lab-host vault key | `vault_addon_cloud_crawler_turnstile_secret` (ADR 0003 here) |
| Lab-host loopback port | not assigned; ADR 0003 leaves it to the website ("the next free port is the website's call"; the Cloud Assessor uses 18083) |
| Image | `docker.io/hybridcloudworks/img-cc-lab-addon`, published on `v*` tags by `publish-images.yml`; only the test image `v0.1.0-rc.1` exists, the first real one is the tag `v0.1.0` (issue 17). The website will pin it by digest in `lab-host/ansible/group_vars/all.yml` `addons[]`. |

## Catalogue row (`frontend/src/data/addons/catalogue.js`)

The website's row is the authority. This is a copy of it as of 2026-10-24 (website pull request #1351, merge commit
`e4e53807`). When this block and the website disagree, the website is right; the other three AddOns' guides had a pasted
row that drifted this way, which is why the source is named.

```js
{
  id: 'cloud-crawler',
  title: 'Cloud architecture drift check',
  summary: 'Upload an export of your Azure resources or your Terraform and see where what is built has drifted from your architecture decisions, with draft decision records and review notes. Nothing you upload is kept beyond two hours.',
  origin: 'https://cloud-crawler.lab.hybridcloudworks.com',
  panePath: '/',
  healthPath: '/api/health',
  providers: ['azure'],
  technology: ['resource-graph', 'terraform', 'architecture-decisions'],
  status: 'coming',
  comingSince: '2026-10-24',
  comingReason: 'The tool is being built. It opens here as soon as its first release is published.',
  capabilities: ['navigate', 'downloads'],
  docsUrl: 'https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn#readme',
  articleSlugs: []
}
```

The row flips to `available` (and `comingSince` and `comingReason` are removed) in one website pull request, once the App
has released, this AddOn has adopted the engine and published its first image, and the owner has created the
human-verification widget and seeded the vault key. `title`, `summary` and `comingReason` obey the site's public-copy rule
(no vendor names; "human verification", "expires after two hours").

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

Base sandbox `allow-scripts allow-same-origin allow-forms`. The website's row lists `navigate` and `downloads`. Those were
copied from the first add-on, not decided for this one. Website issue #1354 settled the rule on 2026-10-24 (pull request
#1359): a pane is granted what it uses, and the two assessment panes hold `downloads` and `clipboard-write`. With the upload
route this pane has the same two controls (a "Download report" button, which saves a file made in the browser, and a "Copy
report" button), and it still never posts a `navigate` message, so when the row is flipped it needs `downloads` and
`clipboard-write` and does not need `navigate`. The row above is the website's and is not changed here. Never
`allow-top-navigation`.

## What `/api/health` reports as capabilities

The status proxy projects the `capabilities` list from health. The lab's list (only ever added to) is `health`, `pane`,
`upload-evidence`, `drift-findings`, `draft-decision-record`, `review-proposals`, `report-markdown`, `report-json`,
`not-an-audit`, `sample-data` and `delete-now`. These are the lab's own names and are different from the sandbox
capabilities of the row above. The MCP server surface and the trusted-caller session API are later releases and are not
in the list.

## Content security policy, both sides

- Site: `frame-src` gains `https://cloud-crawler.lab.hybridcloudworks.com` (derived from `addonOrigins()`) when the row is
  `available`. It has no entry while the row is `coming`.
- AddOn: `frame-ancestors` from `CC_FRAME_ANCESTORS` (default `'none'`, which is what a direct visit sees), set by the lab
  host to the two site origins, equal to the host's `caddy_frame_ancestors`. Both policies are enforced by the browser;
  they must agree.

## Environment (rendered by the website's `addons` role once the row exists)

The settings are the `.env.example` of this repository. The website has no `group_vars` row for this AddOn yet, so the
last column is what the other add-ons use, to be confirmed when the row is written.

| Variable | Store | Expected on the lab host |
|---|---|---|
| `PORT` | `addons[].env` | `8080` |
| `CC_FRAME_ANCESTORS` | `addons[].env` | `https://hybridcloudworks.com https://www.hybridcloudworks.com` |
| `CC_SITE_ORIGINS` | `addons[].env` | `https://hybridcloudworks.com https://www.hybridcloudworks.com` |
| `CC_ALLOWED_ORIGINS` | `addons[].env` | empty (the pane is same-origin with its API) |
| `CC_TRUST_PROXY` | `addons[].env` | `1` (the host's reverse proxy sets `X-Forwarded-For`) |
| `CC_TURNSTILE_SITE_KEY` | `addons[].env` | the widget's public site key |
| `TURNSTILE_SECRET` | vault | `vault_addon_cloud_crawler_turnstile_secret` (`secret_env`) |
| `CC_ALLOW_NO_TURNSTILE` | never set on the host | absent (fail closed) |
| `CC_TTL_MINUTES`, `CC_MAX_ITEMS`, `CC_RATE_LIMIT_POSTS`, `CC_RATE_LIMIT_WINDOW_MINUTES`, `CC_MAX_CONCURRENT` | `addons[].env` | `120`, `200`, `10`, `10`, `2` |

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
