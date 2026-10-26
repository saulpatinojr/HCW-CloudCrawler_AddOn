"""The upload route and what hangs off it: POST /api/uploads, and GET / DELETE of the result with the owner token.

Order of events for a POST, and why this order:

1. The client's rate-limit bucket is spent (cheap, and first, so a flood costs the lab almost nothing).
2. The content type must be JSON, and the declared length must already be within the limit.
3. Human verification. A token is checked against the verification service before a single byte of the body is read,
   let alone parsed, and with no secret configured the route answers 503 rather than skipping the check. The only way
   past that is the local-only override `CC_ALLOW_NO_TURNSTILE=1` with no secret set (`Settings.turnstile_enforced`).
4. The body is streamed in under the size limit and a time limit.
5. The evaluation slot (`CC_MAX_CONCURRENT`) is taken, and the CPU-bound work runs in a worker thread of its own so the
   event loop keeps answering `/api/health`. Before the body is read, a place among the few uploads that may be held in
   memory at once is taken too (twice the evaluation slots), so a crowd of large uploads cannot fill memory while they
   wait for a slot.
6. The result is stored under a random id with a hashed owner token; only the owner token opens it.

Logs from this module carry counts, durations and fixed words only. A refusal is logged by its code and status; an
unexpected failure by the name of its exception class and never its message, which could quote the upload.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from functools import partial
from typing import Any

from fastapi import APIRouter, Request, Response

from cloud_crawler_lab.analysis import Outcome, process_upload
from cloud_crawler_lab.errors import DEFAULT_MESSAGES, ApiError
from cloud_crawler_lab.security import logging as logs
from cloud_crawler_lab.security.limits import READ_DEADLINE_SECONDS, check_declared_length, client_address, read_body
from cloud_crawler_lab.security.redaction import ALLOWED_WORDS
from cloud_crawler_lab.security.turnstile import verify
from cloud_crawler_lab.store import ItemTooLarge

router = APIRouter()

FILES = {
    "report.md": ("text/markdown; charset=utf-8", "cloud-crawler-report.md"),
    "report.json": ("application/json", "cloud-crawler-report.json"),
    "NOT-AN-AUDIT.md": ("text/markdown; charset=utf-8", "NOT-AN-AUDIT.md"),
}
MAX_TOKEN_LENGTH = 128
# What the creating response repeats from the stored result; GET adds the decision, findings and proposals.
CREATED_FIELDS = ("summary", "decision", "evidence", "claims", "listing", "proposalCount", "files")


def _owner_token(request: Request) -> str | None:
    token = request.headers.get("x-owner-token", "").strip()
    return token if 0 < len(token) <= MAX_TOKEN_LENGTH else None


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")


def _json(payload: dict[str, Any], status: int = 200) -> Response:
    return Response(json.dumps(payload, separators=(",", ":")), status_code=status, media_type="application/json")


def _code(exc: ApiError) -> str:
    return exc.code if exc.code in ALLOWED_WORDS else "error"


async def _verify_human(request: Request, client: str) -> None:
    state = request.app.state
    settings = state.settings
    if settings.turnstile_required:
        # siteverify is a blocking urllib call with a 5 s timeout: off the event loop.
        verdict = await asyncio.to_thread(
            verify,
            settings.turnstile_secret or "",
            request.headers.get("x-turnstile-token"),
            client,
            opener=state.verifier,
        )
        if not verdict.ok:
            logs.log_event("turnstile_rejected", codes=len(verdict.codes))
            codes = [code[:64] for code in verdict.codes[:10]]
            raise ApiError(403, "turnstile_failed", "Human verification did not succeed.", {"codes": codes})
        logs.log_event("turnstile_verified")
    elif settings.turnstile_enforced:
        raise ApiError(
            503, "turnstile_not_configured", "Uploads are not available until human verification is configured."
        )


@router.post("/api/uploads", status_code=201)
async def create_upload(request: Request) -> Response:
    try:
        return await _create(request)
    except ApiError as exc:
        logs.log_event("upload_rejected", code=_code(exc), status=exc.status)
        raise


async def _create(request: Request) -> Response:
    state = request.app.state
    settings = state.settings
    started = time.monotonic()

    client = client_address(request, settings.trust_proxy)
    allowed, retry_after = state.limiter.acquire(client)
    if not allowed:
        raise ApiError(
            429,
            "rate_limited",
            DEFAULT_MESSAGES[429],
            {"retryAfterSeconds": retry_after},
            {"Retry-After": str(retry_after)},
        )

    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise ApiError(415, "unsupported_media_type", "Send application/json.")
    check_declared_length(request, settings.max_upload_bytes)

    await _verify_human(request, client)

    if not await state.intake.acquire():
        raise ApiError(503, "overloaded", DEFAULT_MESSAGES[503], headers={"Retry-After": "2"})
    try:
        outcome = await _read_and_evaluate(request)
    finally:
        state.intake.release()

    try:
        stored = state.store.put(outcome.meta, outcome.files, owner=client)
    except ItemTooLarge:
        raise ApiError(422, "result_too_large", "The result is larger than the lab keeps.") from None
    if stored.evicted:
        logs.log_event("session_closed", reason="evicted", count=stored.evicted)

    meta = outcome.meta
    summary = meta["summary"]
    logs.log_event(
        "session_opened",
        files=len(meta["evidence"]),
        resources=sum(item["resourceCount"] for item in meta["evidence"]),
        claims=meta["decision"]["claimCount"],
        findings=meta["listing"]["findingsTotal"],
        contradicted=summary["contradicted"],
        unknown=summary["unknown"],
        proposals=meta["proposalCount"],
        durationMs=int((time.monotonic() - started) * 1000),
        stored=state.store.size,
    )
    payload = {
        "uploadId": stored.id,
        "ownerToken": stored.owner_token,
        "expiresAt": _iso(stored.expires_at),
        "notice": meta["notAnAudit"]["line"],
        **{key: meta[key] for key in CREATED_FIELDS},
    }
    return _json(payload, 201)


async def _read_and_evaluate(request: Request) -> Outcome:
    """Read the body and run it through the pipeline. The body is local here, so it is freed as soon as this returns."""
    state = request.app.state
    body = await read_body(request, state.settings.max_upload_bytes, deadline_seconds=READ_DEADLINE_SECONDS)
    if not await state.bound.acquire():
        raise ApiError(503, "overloaded", DEFAULT_MESSAGES[503], headers={"Retry-After": "2"})
    job = asyncio.get_running_loop().run_in_executor(
        state.pool, partial(process_upload, body, max_rows=state.settings.max_rows)
    )
    # The slot is given back when the thread has really finished, not when this request stops waiting for it: a request
    # that is cancelled mid-evaluation must not let a third evaluation start beside the two still running.
    job.add_done_callback(partial(_finished, state))
    try:
        # `wait` does not cancel the job when this request is cancelled (`shield` would, and would also log the job's
        # exception text through the event loop's own handler); the callback above gives the slot back and reads it.
        await asyncio.wait({job})
        return job.result()
    except ApiError:
        raise
    except Exception as exc:  # noqa: BLE001 - whatever it is, the visitor gets the plain 500 and the log gets a class name
        logs.log_event("upload_failed", scrubbed=type(exc).__name__)
        raise ApiError(500, "internal_error", DEFAULT_MESSAGES[500]) from None


def _finished(state, job: asyncio.Future) -> None:
    state.bound.release()
    if not job.cancelled():
        job.exception()  # read it, so a request that gave up waiting leaves no "never retrieved" noise


def _load(request: Request, upload_id: str):
    view = request.app.state.store.get(upload_id, _owner_token(request))
    if view is None:
        raise ApiError(404, "not_found", "Not found.")
    return view


def _detail(view, upload_id: str) -> Response:
    report = json.loads(view.files["report.json"])
    result = report["result"]
    return _json(
        {
            "uploadId": upload_id,
            "expiresAt": _iso(view.expires_at),
            **view.meta,
            "decision": report["decision"],
            "evaluatedAt": result["evaluatedAt"],
            "findings": result["findings"],
            "contradictions": result["contradictions"],
            "proposals": result["proposals"],
        }
    )


@router.get("/api/uploads/{upload_id}")
async def get_upload(request: Request, upload_id: str) -> Response:
    view = _load(request, upload_id)
    return await asyncio.to_thread(_detail, view, upload_id)  # reading back up to 8 MB is not work for the event loop


@router.get("/api/uploads/{upload_id}/files/{name}")
async def get_file(request: Request, upload_id: str, name: str) -> Response:
    view = _load(request, upload_id)
    if name not in FILES or name not in view.files:
        raise ApiError(404, "not_found", "Not found.")
    media_type, download_name = FILES[name]
    return Response(
        view.files[name],
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )


@router.delete("/api/uploads/{upload_id}")
async def delete_upload(request: Request, upload_id: str) -> dict:
    store = request.app.state.store
    if not store.delete(upload_id, _owner_token(request)):
        raise ApiError(404, "not_found", "Not found.")
    logs.log_event("session_closed", reason="deleted", stored=store.size)
    return {"deleted": True}
