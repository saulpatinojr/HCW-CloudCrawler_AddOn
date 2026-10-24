# Routes on the website

| Route | Page | Notes |
|---|---|---|
| `/tools/cloud-crawler` | `frontend/src/pages/tools/CloudCrawlerPage.jsx` -> `<AddOnPanePage addonId="cloud-crawler" />` | One `lazyPage` wrapper in `App.jsx` (routes stay hand-declared, not a `:id` parameter); `staticRoutes.cloudCrawler` in `routeFactory.ts`. Added by website pull request #1351. |

- Pre-render: `scripts/prerender-entry.jsx` derives `ADDON_ROUTES` from the catalogue, so the route is pre-rendered. While
  the row is `coming` the built page is the explainer (title, summary, `comingReason`, a link back) and frames nothing.
- Tools menu: the Header derives its items from `availableAddons`, so the item appears only when the row flips to
  `available`. A real-browser check of the `coming` page on 2026-10-24 found no link to it from `/azure`.
- No provider-scoped variant (`/azure/tools/cloud-crawler` is not created); `providers: ['azure']` is hub-card metadata.
- This AddOn's own routes will be in its API description once it has an engine; the site calls only `GET /api/health`,
  server side, through the status proxy.
