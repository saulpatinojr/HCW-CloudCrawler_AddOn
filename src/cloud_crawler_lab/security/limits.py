"""Body cap: stream and stop reading past the limit (the response goes out before the body is drained).

Two limits apply while a body arrives: its size, checked chunk by chunk (and up front against the declared length),
and the time it may take, so a client that sends one byte a minute cannot hold a connection for the whole two hours.
"""

from __future__ import annotations

import asyncio
import ipaddress

from fastapi import Request
from starlette.requests import ClientDisconnect

from cloud_crawler_lab.errors import ApiError

API_LIMITS = {"max_upload_bytes": 5 * 1024 * 1024, "max_rows": 5_000, "max_items": 200, "ttl_minutes": 120}
# From the first chunk requested to the last one received. A 5 MB file over a slow mobile link still fits in this.
READ_DEADLINE_SECONDS = 30.0


def _too_large(limit: int) -> ApiError:
    return ApiError(413, "too_large", "The upload is larger than the limit.", {"maxUploadBytes": limit})


def check_declared_length(request: Request, limit: int) -> None:
    """Refuse a body whose declared length is already past the limit, before spending anything on it."""
    declared = request.headers.get("content-length")
    if declared and declared.isascii() and declared.isdigit() and int(declared) > limit:
        raise _too_large(limit)


async def read_body(request: Request, limit: int, *, deadline_seconds: float | None = None) -> bytes:
    check_declared_length(request, limit)
    chunks: list[bytes] = []
    total = 0

    async def drain() -> None:
        nonlocal total
        async for chunk in request.stream():
            total += len(chunk)
            if total > limit:
                raise _too_large(limit)
            chunks.append(chunk)

    try:
        async with asyncio.timeout(deadline_seconds):
            await drain()
    except TimeoutError:
        raise ApiError(408, "request_timeout", "The upload took too long to arrive.") from None
    except ClientDisconnect:
        raise ApiError(400, "client_disconnected", "The connection closed before the upload arrived.") from None
    return b"".join(chunks)


def _bucket(address: str) -> str:
    """One key per client: an IPv4 address as it is, an IPv6 address as its /64 (one subscriber holds a whole /64 and
    could otherwise spend a fresh bucket per address). Text that is not an address is a key of its own, as before."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return address[:64]
    return str(ipaddress.ip_network(f"{ip}/64", strict=False)) if ip.version == 6 else str(ip)


def client_address(request: Request, trust_proxy: bool) -> str:
    """The key a client is rate limited by. Behind the lab host's proxy (`CC_TRUST_PROXY=1`) it is the first
    X-Forwarded-For entry, which that proxy writes itself: Caddy's reverse_proxy ignores an incoming value unless its
    sender is a configured trusted proxy (https://caddyserver.com/docs/caddyfile/directives/reverse_proxy, "Defaults").
    A value that is not an IP address is never used as a key."""
    if trust_proxy:
        first = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        try:
            ipaddress.ip_address(first)
        except ValueError:
            pass
        else:
            return _bucket(first)
    return _bucket(request.client.host) if request.client else "unknown"
