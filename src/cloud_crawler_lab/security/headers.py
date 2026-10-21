"""Security headers on every response (pure ASGI middleware, so streaming bodies are untouched)."""

from __future__ import annotations

from cloud_crawler_lab import ADDON_ID, __version__
from cloud_crawler_lab.config import Settings

VERIFICATION_ORIGIN = "https://challenges.cloudflare.com"


def content_security_policy(settings: Settings) -> str:
    script_src = "'self'"
    frame_src = "'none'"
    if settings.turnstile_site_key:
        script_src += f" {VERIFICATION_ORIGIN}"
        frame_src = VERIFICATION_ORIGIN
    return (
        "default-src 'self'; "
        f"script-src {script_src}; "
        "style-src 'self'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        f"frame-src {frame_src}; "
        f"frame-ancestors {settings.frame_ancestors}; "
        "base-uri 'none'; "
        "form-action 'self'; "
        "object-src 'none'"
    )


def security_headers(settings: Settings) -> list[tuple[bytes, bytes]]:
    headers = [
        (b"x-addon-id", ADDON_ID.encode()),
        (b"x-addon-version", __version__.encode()),
        (b"x-content-type-options", b"nosniff"),
        (b"referrer-policy", b"no-referrer"),
        (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
        (b"content-security-policy", content_security_policy(settings).encode()),
        (b"cross-origin-opener-policy", b"same-origin"),
    ]
    if settings.frame_ancestors.strip() == "'none'":
        headers.append((b"x-frame-options", b"DENY"))
    return headers


def cache_control_for(path: str) -> bytes:
    if path.startswith("/api/"):
        return b"no-store"
    if path in ("", "/", "/index.html"):
        return b"no-cache"
    return b"public, max-age=300"


class SecurityHeadersMiddleware:
    def __init__(self, app, settings: Settings) -> None:
        self.app = app
        self.static_headers = security_headers(settings)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                existing = {k.lower() for k, _ in message.get("headers", [])}
                extra = [(k, v) for k, v in self.static_headers if k not in existing]
                if b"cache-control" not in existing:
                    extra.append((b"cache-control", cache_control_for(path)))
                message["headers"] = list(message.get("headers", [])) + extra
            await send(message)

        await self.app(scope, receive, send_with_headers)
