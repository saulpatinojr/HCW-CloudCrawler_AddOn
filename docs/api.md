# The lab's HTTP API

What the lab answers on `https://cloud-crawler.lab.hybridcloudworks.com` (and on `127.0.0.1` when you run it yourself).
The website calls only `GET /api/health`; everything else is the pane's, and a visitor's own scripts may use it too.
Every `/api` answer is sent with `Cache-Control: no-store`, and every error has the same envelope:

```json
{ "error": { "code": "too_large", "message": "The upload is larger than the limit.", "details": { "maxUploadBytes": 5242880 } } }
```

`details` holds codes, counts, positions (`claimIndex`, `evidenceIndex`) and field paths (`decision.claims[0].severity`).
It never repeats a value you uploaded, and neither do the logs.

## Routes

| Route | What it does |
| --- | --- |
| `GET /api/health` | Flat health answer for the website's status proxy: `id`, `version`, `edition`, `capabilities`, `asOf`, `siteOrigins`, `turnstile`, `azureConnectivity`, `limits`. |
| `POST /api/uploads` | The upload (below). `201` with the owner token, the summary and the claims table. |
| `GET /api/uploads/{id}` | The whole result: decision record, evidence notes, per-claim counts, findings, contradictions, review proposals and the not-an-audit note. Needs `X-Owner-Token`. |
| `GET /api/uploads/{id}/files/{name}` | One of the three report files: `report.md`, `report.json`, `NOT-AN-AUDIT.md`. Needs `X-Owner-Token`. |
| `DELETE /api/uploads/{id}` | Deletes the result now. Needs `X-Owner-Token`. |
| `GET /api/samples/{name}` | A fictional sample from [`samples/`](../samples/README.md): `sample-resource-graph.json`, `decision-starter.json`, `decision-zone-redundancy.json`, `decision-wave-one.json`. |

A wrong id, a wrong or missing owner token and an expired result all answer the same `404`.

## The upload

```text
POST /api/uploads
Content-Type: application/json
X-Turnstile-Token: <the human-verification token>      (required unless the lab runs in its local-only mode)
```

```json
{
  "evidence": [ { "kind": "arg-export", "name": "export.json", "content": { "count": 1, "data": [ "..." ] } } ],
  "decision": { "title": "...", "claims": [ { "statement": "...", "detectorId": "public-access-disabled",
                "expectation": { "property": "publicNetworkAccessDisabled", "operator": "eq", "value": true } } ] }
}
```

- `evidence`: 1 to 5 files. `kind` is `arg-export` (a Resource Graph export: an array, or an object with a `data` array),
  `tf-state` (version 4) or `tf-plan` (`format_version` 1.x with `resource_changes`). `name` is optional and must look like
  `plain name.json`. This version of the engine reads Resource Graph exports only; a Terraform file is recorded with a
  fingerprint and the response marks it `readByDetectors: false`.
- `decision`: the App's `adr_create` input, with the limits below. It is recorded as a **draft** (`status` may be `draft` or
  `proposed`). The detectors are listed in [`samples/README.md`](../samples/README.md).

### What happens, in order

1. The client's rate limit is spent (10 uploads per 10 minutes by default); `429` with `Retry-After` when it is empty. The client is the peer address, or behind the lab host's proxy (`CC_TRUST_PROXY=1`) the first `X-Forwarded-For` entry when it is an IP address (an IPv6 client counts as its /64). The proxy writes that header itself: Caddy's `reverse_proxy` ignores an incoming value unless its sender is a configured trusted proxy ([Caddy: reverse_proxy, Defaults](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)).
2. The content type must be `application/json` (`415`), and a declared length past the limit is refused (`413`).
3. **Human verification** (`403 turnstile_failed`). With no secret configured the answer is `503 turnstile_not_configured`;
   the local-only override `CC_ALLOW_NO_TURNSTILE=1` works only when no secret is set.
4. The body is read, at most 5 MB and within 30 seconds (`413`, `408`).
5. A place among the uploads held in memory at once is taken before the body is read (`503 overloaded` with
   `Retry-After: 2` when none is free), then an evaluation slot (the same answer when both are busy), and the body is
   parsed, checked, ingested by the engine, evaluated and bundled in a worker thread of its own.
6. The result is stored, and the answer carries `uploadId`, `ownerToken` (shown once) and `expiresAt`.

### Limits

| Limit | Value | Error |
| --- | --- | --- |
| Body | 5 MB, and 30 s to arrive | `413 too_large`, `408 request_timeout` |
| Rows (resources) | 5,000 across all files | `422 too_many_rows` |
| Files | 5 | `400 invalid_request` |
| Claims in the decision | 20 | `400 invalid_request` |
| Claims times resources read | 25,000 (about 120 MB while evaluating) | `422 too_many_findings` |
| Nesting, objects and arrays, values, one string | depth 64; 100,000 objects and arrays; 1 million values; 65,536 characters; at most 16 `eyJ` in one string | `422 too_complex` |
| Tags and zones on one resource | 100 and 100 | `422 ingestion_failed` |
| The decision part of the request | 20,000 values, no object over 128 keys, no list over 1,000 | `400 invalid_request` |
| Results held | 200, and 64 MB in all (oldest first); one client (the address the rate limit uses) may hold a tenth of the results and a quarter of the bytes, and loses its own oldest first | none: the oldest is dropped |
| Uploads in memory at once | twice the evaluation slots (4 by default), counted before the body is read | `503 overloaded` |
| Time held | 120 minutes | `404` afterwards |
| Findings listed in a result | 1,000 (contradicted, then unknown, then supported); not-applicable are counted, not listed | `listing` says what was left out |

Decision text: a title up to 200 characters, other text fields up to 4,000 (lists of up to 20 lines of 500), a claim
statement up to 500, up to 10 parameters per claim, up to 30 resource types, 10 tag selectors, 10 name globs (at most 8
`*` each) and 100 values in one `in` comparison. A claim's values are strings (up to 256 characters), numbers,
booleans or null, never lists or objects.

### Errors you can expect

| Status | Code | Meaning |
| --- | --- | --- |
| 400 | `invalid_json` | Not UTF-8 JSON (NaN, Infinity and lone surrogates included). |
| 400 | `invalid_request` | The shape is wrong; `details.fields` names the fields. |
| 403 | `turnstile_failed` | Human verification did not succeed; `details.codes` has the verification service's codes. |
| 413 / 408 | `too_large` / `request_timeout` | Body past the size limit, or too slow. |
| 415 | `unsupported_media_type` | Anything but JSON; archives and YAML are never opened. |
| 422 | `ingestion_failed` | A file is not the kind it says; `details.evidenceIndex` and `reason` say which. |
| 422 | `invalid_decision` | A claim cannot be evaluated; `details.claimIndex` and `reason` (`unknown_detector` lists the known ones). |
| 422 | `too_many_rows`, `too_many_findings`, `too_complex`, `result_too_large` | A limit above. |
| 400 | `client_disconnected` | The connection closed before the body arrived. |
| 429 / 503 | `rate_limited`, `overloaded`, `turnstile_not_configured` | Try later, or the lab is not set up for uploads. |

Every result carries the note that it is not an audit: the `notice` of the creating answer, `notAnAudit` in the full
result, the last line of `report.md`, `lab.notAnAudit` in `report.json`, and the file `NOT-AN-AUDIT.md`.
