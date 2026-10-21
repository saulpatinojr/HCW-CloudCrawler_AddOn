"""Body cap: stream and stop reading past the limit (the response goes out before the body is drained)."""

from __future__ import annotations

from fastapi import Request

from cloud_crawler_lab.errors import ApiError

API_LIMITS = {"max_upload_bytes": 5 * 1024 * 1024, "max_rows": 5_000, "max_items": 200, "ttl_minutes": 120}


async def read_body(request: Request, limit: int) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise ApiError(413, "too_large", "The upload is larger than the limit.", {"maxUploadBytes": limit})
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise ApiError(413, "too_large", "The upload is larger than the limit.", {"maxUploadBytes": limit})
        chunks.append(chunk)
    return b"".join(chunks)


def client_address(request: Request, trust_proxy: bool) -> str:
    if trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "")
        first = forwarded.split(",")[0].strip()
        if first:
            return first[:64]
    return request.client.host if request.client else "unknown"
