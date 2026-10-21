"""Human-verification siteverify over stdlib urllib, 5 s timeout, action must echo back as cloud-crawler-upload."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field

from cloud_crawler_lab.config import TURNSTILE_ACTION

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TIMEOUT_SECONDS = 5.0
MAX_TOKEN_LENGTH = 2048

Opener = Callable[[urllib.request.Request, float], bytes]


@dataclass(frozen=True)
class Verdict:
    ok: bool
    codes: list[str] = field(default_factory=list)


def _default_opener(request: urllib.request.Request, timeout: float) -> bytes:
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https URL
        return response.read()


def verify(secret: str, token: str | None, remote_ip: str | None, *, opener: Opener | None = None) -> Verdict:
    if not token or len(token) > MAX_TOKEN_LENGTH:
        return Verdict(False, ["missing-input-response"])
    form = {"secret": secret, "response": token}
    if remote_ip:
        form["remoteip"] = remote_ip
    request = urllib.request.Request(
        SITEVERIFY_URL,
        data=urllib.parse.urlencode(form).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    try:
        raw = (opener or _default_opener)(request, TIMEOUT_SECONDS)
        payload = json.loads(raw.decode("utf-8"))
    except urllib.error.URLError, TimeoutError, OSError, ValueError:
        return Verdict(False, ["verification-unavailable"])
    if not isinstance(payload, dict):
        return Verdict(False, ["verification-unavailable"])
    codes = [str(c) for c in payload.get("error-codes", []) if isinstance(c, str)]
    if payload.get("success") is not True:
        return Verdict(False, codes or ["invalid-input-response"])
    if payload.get("action") != TURNSTILE_ACTION:
        return Verdict(False, ["action-mismatch"])
    return Verdict(True, [])
