# 0004. The upload route: one verified request, evidence plus a decision, results in memory only

- **Status:** Accepted
- **Date:** 2026-10-26
- **Owners:** Workload owner and architecture owner
- **Issue:** [16](https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/issues/16) (tracking issue [17](https://github.com/saulpatinojr/HCW-CloudCrawler_AddOn/issues/17))

## Context

The engine (`cloud-crawler-core` 0.1.0) was adopted but nothing called it, so the pane's file picker was disabled and
the website's row ("see where what is built has drifted from your architecture decisions, with draft decision records
and review notes") had nothing behind it. The engine checks a **decision** (claims about what should be true) against
**evidence** (what is built), so an upload needs both. The route takes files from strangers on a public lab, so how the
body is verified, bounded and kept matters more than the route's shape.

## Decision

1. **One request carries both halves.** `POST /api/uploads` takes one JSON object: `evidence` (1 to 5 files, each
   `{kind, name?, content}` with `kind` one of `arg-export`, `tf-state`, `tf-plan`) and `decision` (the App's
   `DecisionInput`, with limits). The pane builds it from the files the visitor picks. One request means one human
   verification, because a verification token works once. The decision is always recorded as a **draft**; accepting
   one is a person's act upstream and never happens here.
2. **Order of checks.** Rate limit, content type and declared length, **human verification, then** the body is read
   (under a size limit and a 30 second deadline), then parsed. Without a secret the route answers 503; the only way
   around verification is the existing local-only override with no secret set (`CC_ALLOW_NO_TURNSTILE=1`).
3. **Bounded before the engine sees it.** The bytes are counted for brackets, parsed as strict UTF-8 JSON (NaN,
   Infinity and lone surrogates refused), then walked without recursion for depth (64), node count and string length.
   Rows (5,000 across all files) are counted by the engine for Resource Graph exports and by the lab for Terraform
   files. The lab's own source cannot write a file, load YAML, open an archive or run a regular expression over
   uploaded text. The engine does run one: its secret-redaction pattern (`eyJ...` then a dot) is quadratic on a string
   that repeats `eyJ` with no dot, so the lab refuses a string with more than 16 of them until the engine's pattern is
   fixed upstream ([App issue 53](https://github.com/saulpatinojr/HCW-CloudCrawler_App/issues/53); a possessive quantifier measured 0.0008 s on the string that took 1.2 s). The parts of the request
   that pydantic validates entry by entry (the decision) get a size budget first, because pydantic writes one error per
   bad entry (250,000 entries measured 1.3 GB).
4. **The engine does the work, the lab decides what is kept.** `ingest`, `evaluate_decision` and `bundle` are the
   engine's. The engine answers every claim for every resource, and holds each answer (about 3.6 KB) while it works,
   so claims times resources read is capped at 25,000 (measured: about 120 MB for one evaluation, 238 MiB peak with
   three max-size uploads at once in a 512 MiB container). The kept result lists the findings that matter
   (contradicted, then unknown, then supported; at most 1,000), counts the rest exactly in the summary, says what it
   left out, and shortens echoed values. Terraform kinds are accepted and recorded with a fingerprint, but the
   engine reads only Resource Graph exports, so claims about Terraform stay `unknown`, and the response says so.
5. **Memory only, two hours, owner token.** Results live in an in-process store: random version 4 ids, an owner token
   shown once and kept as a SHA-256, constant-time comparison, the same 404 for a wrong id, a wrong token and an expired
   result, 200 results and 64 MB at most (oldest first, but one client may hold only a tenth of the results and a
   quarter of the bytes, so one client's uploads push out its own results first), expiry after 120 minutes with a
   sweep, emptied at shutdown. There is no temporary directory because nothing is written to disk.
6. **Logs and errors carry no content.** Log lines hold counts and fixed words; a refusal is logged by code and status,
   an unexpected failure by its exception class and never its message. Error bodies name a field path, a position or a
   reason code, never a value the visitor sent.
7. **Capabilities are added, not renamed.** `edition.py` gains `upload-evidence`, `drift-findings`,
   `draft-decision-record`, `review-proposals`, `report-markdown`, `report-json`, `not-an-audit`, `sample-data` and
   `delete-now`. The MCP server surface and the trusted-caller session API stay later releases and are not listed.

## Alternatives considered

| Alternative | Benefits | Drawbacks | Reason not selected |
| --- | --- | --- | --- |
| Several routes (create a session, add a decision, add evidence, evaluate) | Mirrors the App's tool catalogue | One verification token per call, or a verified session with a new lifetime to secure; more state to isolate | One request is simpler to verify and to bound; the session API is the later release |
| Multipart upload | The usual way to send a file | Needs a multipart parser from strangers (a new dependency and attack surface) for two JSON documents | Rejected for parser safety |
| Keep every finding, as the engine's bundle does | Nothing is left out | 100,000 findings are tens of megabytes per result, times 200 | Rejected: a small upload must not become a large stored result |
| Read Terraform in the lab | The row promises Terraform | Normalising Terraform is engine logic, and engine changes go upstream first ([App issue 54](https://github.com/saulpatinojr/HCW-CloudCrawler_App/issues/54)) | Recorded and reported as unread until the engine reads it |
| Write results to a temporary directory | Survives a restart | Disk writes on a public lab, and the container is read-only | Rejected: memory only, as the sibling lab does |

## Consequences

- A visitor needs a decision as well as an export. The pane offers a starter decision and two samples, and a file
  picker for their own.
- Memory is the limit: at most 64 MB of results plus the work in flight (two evaluations at a time, and no more than
  four bodies held in memory at once). The measurements are in `VALIDATION.md`: 25,000 findings is about 120 MB while
  evaluating, the worst accepted document shape (95,000 tiny objects in one row) 55 MB, and three max-size uploads at
  once peaked at 269 MiB in a 512 MiB container.
- A restart empties every result, which is the stated behaviour ("expires after two hours").
- The website's row still lists `navigate` and `downloads`; the pane now uses `downloads` and `clipboard-write` (a
  download and a copy button) and never `navigate`. That is the website's pull request when it flips the row. The pane
  asks twice on the delete button instead of opening a dialog, because the frame's sandbox has no `allow-modals`.
- The decision is recorded as a draft or a proposal (`status` may be `draft` or `proposed`); never accepted.

## Validation

Implementation owner: the workload owner. Evidence: `tests/unit/test_upload_api.py`, `tests/unit/test_inputs.py`,
`tests/unit/test_decisions.py`, `tests/unit/test_evidence.py`, `tests/unit/test_store.py`,
`tests/security/test_upload_hardening.py` (content-free logs, no disk writes, hostile documents, bounded results) and
`tests/acceptance/test_upload_acceptance.py` (the App's golden verdicts on the sample estate), plus the image run in
`VALIDATION.md`.

## Rollback or revisit trigger

Remove the upload routers from `app.py`; the capability names stay in the list, because capabilities are only ever
added. Revisit when the engine reads Terraform (add nothing here; the next core bump brings it), when the session API
arrives (it may replace the one-request shape for the website's chat path), or if memory pressure shows on the lab host.
