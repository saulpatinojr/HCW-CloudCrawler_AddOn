"""Exact-origin CORS. Preflight answers 204 for an allowed origin and 403 otherwise; no wildcard, ever."""

from __future__ import annotations

import json

ALLOW_HEADERS = b"content-type, x-owner-token, x-turnstile-token"
ALLOW_METHODS = b"GET, POST, DELETE, OPTIONS"
EXPOSE_HEADERS = b"content-disposition, x-addon-id, x-addon-version, retry-after"
MAX_AGE = b"600"


class ExactOriginCorsMiddleware:
    def __init__(self, app, allowed_origins: tuple[str, ...]) -> None:
        self.app = app
        self.allowed = {o.encode() for o in allowed_origins}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        origin = headers.get(b"origin")
        if origin is None:
            await self.app(scope, receive, send)
            return
        allowed = origin in self.allowed
        if scope["method"] == "OPTIONS" and b"access-control-request-method" in headers:
            if allowed:
                await self._respond(
                    send,
                    204,
                    [
                        (b"access-control-allow-origin", origin),
                        (b"access-control-allow-methods", ALLOW_METHODS),
                        (b"access-control-allow-headers", ALLOW_HEADERS),
                        (b"access-control-max-age", MAX_AGE),
                        (b"vary", b"Origin"),
                    ],
                )
            else:
                body = json.dumps({"error": {"code": "forbidden", "message": "Origin not allowed."}}).encode()
                await self._respond(send, 403, [(b"content-type", b"application/json")], body)
            return

        async def send_with_cors(message):
            if message["type"] == "http.response.start" and allowed:
                message["headers"] = list(message.get("headers", [])) + [
                    (b"access-control-allow-origin", origin),
                    (b"access-control-expose-headers", EXPOSE_HEADERS),
                    (b"vary", b"Origin"),
                ]
            await send(message)

        await self.app(scope, receive, send_with_cors)

    @staticmethod
    async def _respond(send, status: int, headers: list[tuple[bytes, bytes]], body: bytes = b"") -> None:
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": headers + [(b"content-length", str(len(body)).encode())],
            }
        )
        await send({"type": "http.response.body", "body": body})
