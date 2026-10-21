"""Settings from the environment (prefix CC_). No secret is ever logged or echoed; TURNSTILE_SECRET is read once."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TURNSTILE_ACTION = "cloud-crawler-upload"


# Upper bound for every numeric setting: large enough for any real deployment, small enough that every derived value
# (minutes * 60, seconds into asyncio/datetime arithmetic) stays representable; Python ints do not overflow, but the
# clocks and sleeps they feed do.
MAX_SETTING = 1_000_000_000


def _int(env: Mapping[str, str], key: str, default: int, *, minimum: int = 0) -> int:
    raw = env.get(key, "").strip()
    if not raw:
        return default
    if not raw.isdigit() or len(raw) > 10:
        raise ValueError(f"{key} must be an integer between {minimum} and {MAX_SETTING}")
    value = int(raw)
    if value < minimum or value > MAX_SETTING:
        raise ValueError(f"{key} must be between {minimum} and {MAX_SETTING}")
    return value


def _flag(env: Mapping[str, str], key: str) -> bool:
    return env.get(key, "").strip().lower() in {"1", "true", "yes", "on"}


def _origins(env: Mapping[str, str], key: str) -> tuple[str, ...]:
    raw = env.get(key, "").replace(",", " ")
    origins = []
    for item in raw.split():
        item = item.strip().rstrip("/")
        if not item.startswith(("https://", "http://")) or " " in item:
            raise ValueError(f"{key} entries must be origins (scheme://host[:port])")
        origins.append(item)
    return tuple(dict.fromkeys(origins))


@dataclass(frozen=True)
class Settings:
    port: int = 8080
    allowed_origins: tuple[str, ...] = ()
    frame_ancestors: str = "'none'"
    site_origins: tuple[str, ...] = ()
    turnstile_secret: str | None = field(default=None, repr=False)
    turnstile_site_key: str | None = None
    allow_no_turnstile: bool = False
    ttl_minutes: int = 120
    max_items: int = 200
    rate_limit_posts: int = 10
    rate_limit_window_minutes: int = 10
    max_concurrent: int = 2
    trust_proxy: bool = False
    log_silent: bool = False
    static_dir: Path = ROOT / "web"
    max_upload_bytes: int = 5 * 1024 * 1024
    max_rows: int = 5_000

    @property
    def turnstile_required(self) -> bool:
        return self.turnstile_secret is not None and self.turnstile_secret != ""

    @property
    def turnstile_enforced(self) -> bool:
        """Uploads are gated unless the secret is absent AND the local-only override is set (fail closed otherwise)."""
        return self.turnstile_required or not self.allow_no_turnstile

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        secret = env.get("TURNSTILE_SECRET", "").strip() or None
        frame_ancestors = env.get("CC_FRAME_ANCESTORS", "").strip() or "'none'"
        if any(ch in frame_ancestors for ch in ";\n\r"):
            raise ValueError("CC_FRAME_ANCESTORS must be a single CSP source list")
        static_dir = Path(env.get("CC_STATIC_DIR", "").strip() or cls.static_dir)
        return cls(
            port=_int(env, "PORT", 8080, minimum=1),
            allowed_origins=_origins(env, "CC_ALLOWED_ORIGINS"),
            frame_ancestors=frame_ancestors,
            site_origins=_origins(env, "CC_SITE_ORIGINS"),
            turnstile_secret=secret,
            turnstile_site_key=env.get("CC_TURNSTILE_SITE_KEY", "").strip() or None,
            allow_no_turnstile=_flag(env, "CC_ALLOW_NO_TURNSTILE"),
            ttl_minutes=_int(env, "CC_TTL_MINUTES", 120, minimum=1),
            max_items=_int(env, "CC_MAX_ITEMS", 200, minimum=1),
            rate_limit_posts=_int(env, "CC_RATE_LIMIT_POSTS", 10, minimum=1),
            rate_limit_window_minutes=_int(env, "CC_RATE_LIMIT_WINDOW_MINUTES", 10, minimum=1),
            max_concurrent=_int(env, "CC_MAX_CONCURRENT", 2, minimum=1),
            trust_proxy=_flag(env, "CC_TRUST_PROXY"),
            log_silent=_flag(env, "CC_LOG_SILENT"),
            static_dir=static_dir,
        )
