# Routes on the website

| Route | Page | Notes |
|---|---|---|
| `/tools/cloud-crawler` | `frontend/src/pages/tools/CloudCrawlerPage.jsx` -> `<AddOnPanePage addonId="cloud-crawler" />` | One `lazyPage` wrapper in `App.jsx` (routes stay hand-declared, not a `:id` parameter); `staticRoutes.cloudCrawler` in `routeFactory.ts`. Added by website pull request #1351; the row became `available` in website pull request [1413](https://github.com/saulpatinojr/HCW-HybridCloudWorks/pull/1413). |

- Pre-render: `scripts/prerender-entry.jsx` derives `ADDON_ROUTES` from the catalogue, so the route is pre-rendered. While
  a row is `coming` the built page is the explainer (title, summary, `comingReason`, a link back) and frames nothing; this
  row is `available`, so its page holds the pane.
- Tools menu: the Header derives its items from `availableAddons`, so the item appears when the row is `available` (and the
  website has been deployed). A real-browser check of the `coming` page on 2026-10-24 found no link to it from `/azure`.
- No provider-scoped variant (`/azure/tools/cloud-crawler` is not created); `providers: ['azure']` is hub-card metadata.
- This AddOn's own routes are described in [`docs/api.md`](../api.md); the site calls only `GET /api/health`, server side,
  through the status proxy. The pane (inside the frame) calls `POST /api/uploads`, `GET` and `DELETE /api/uploads/{id}`,
  `GET /api/uploads/{id}/files/{name}` and `GET /api/samples/{name}` on its own origin, with the visitor's human-verification
  token and owner token as headers. The frame URL carries `?theme=` only; the pane reads nothing else from the query.
