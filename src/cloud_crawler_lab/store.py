"""The results the lab holds for visitors: in memory only, two hours at most, one visitor's data invisible to another.

- Ids are random version-4 UUIDs. The owner token is random too, handed out once, and only its SHA-256 is kept;
  a lookup compares in constant time and answers the same "not found" for an unknown id, a wrong token and an
  expired result, so nothing says which of the three it was.
- Nothing is ever written to disk. A restart, a shutdown or `clear()` is the whole of "removal on exit".
- The store is bounded two ways: a number of results (`CC_MAX_ITEMS`, 200) and a number of bytes
  (`CC_MAX_STORE_MB`). When either would be exceeded the oldest results go first.
- One client cannot push everyone else out: each client (the key the rate limiter uses) may hold a tenth of the results
  and a quarter of the bytes, and past that its own oldest results go first, before anyone else's are touched.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any


class ItemTooLarge(ValueError):
    """One result alone is bigger than the whole store may hold."""


@dataclass(frozen=True)
class Stored:
    id: str
    owner_token: str
    expires_at: datetime
    evicted: int


@dataclass(frozen=True)
class View:
    meta: dict[str, Any]
    files: dict[str, bytes]
    expires_at: datetime


@dataclass
class _Entry:
    meta: dict[str, Any]
    files: dict[str, bytes]
    size: int
    token_hash: bytes
    created: float
    expires: float
    owner: str = ""
    expires_wall: datetime = field(default_factory=lambda: datetime.now(UTC))


def _hash(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()


class UploadStore:
    def __init__(
        self,
        ttl_seconds: float,
        max_items: int,
        max_bytes: int,
        *,
        per_owner_items: int | None = None,
        per_owner_bytes: int | None = None,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._ttl = ttl_seconds
        self._max_items = max_items
        self._max_bytes = max_bytes
        self._per_owner_items = per_owner_items if per_owner_items is not None else max(1, max_items // 10)
        self._per_owner_bytes = per_owner_bytes if per_owner_bytes is not None else max(1, max_bytes // 4)
        self._clock = clock
        self._wall = wall_clock
        self._items: dict[str, _Entry] = {}
        self._bytes = 0
        self._lock = threading.Lock()

    def put(self, meta: dict[str, Any], files: dict[str, bytes], owner: str = "") -> Stored:
        size = sum(len(data) for data in files.values())
        if size > self._max_bytes:
            raise ItemTooLarge("result larger than the store")
        token = secrets.token_urlsafe(24)
        now = self._clock()
        wall = self._wall()
        entry = _Entry(
            meta, dict(files), size, _hash(token), now, now + self._ttl, owner, wall + timedelta(seconds=self._ttl)
        )
        evicted = 0
        with self._lock:
            self._sweep_locked(now)
            while True:
                mine = [key for key, item in self._items.items() if owner and item.owner == owner]
                held = sum(self._items[key].size for key in mine)
                if not mine or (len(mine) < self._per_owner_items and held + size <= self._per_owner_bytes):
                    break
                oldest = min(mine, key=lambda k: self._items[k].created)
                self._bytes -= self._items.pop(oldest).size
                evicted += 1
            while self._items and (len(self._items) >= self._max_items or self._bytes + size > self._max_bytes):
                oldest = min(self._items, key=lambda k: self._items[k].created)
                self._bytes -= self._items.pop(oldest).size
                evicted += 1
            upload_id = str(uuid.uuid4())
            self._items[upload_id] = entry
            self._bytes += size
        return Stored(upload_id, token, entry.expires_wall, evicted)

    def _lookup_locked(self, upload_id: str, token: str | None) -> _Entry | None:
        if not token or not upload_id:
            return None
        entry = self._items.get(upload_id)
        if entry is None or entry.expires <= self._clock():
            return None
        return entry if hmac.compare_digest(entry.token_hash, _hash(token)) else None

    def get(self, upload_id: str, token: str | None) -> View | None:
        with self._lock:
            entry = self._lookup_locked(upload_id, token)
            return None if entry is None else View(entry.meta, entry.files, entry.expires_wall)

    def delete(self, upload_id: str, token: str | None) -> bool:
        with self._lock:
            if self._lookup_locked(upload_id, token) is None:
                return False
            self._bytes -= self._items.pop(upload_id).size
            return True

    def sweep(self, now: float | None = None) -> int:
        with self._lock:
            return self._sweep_locked(self._clock() if now is None else now)

    def _sweep_locked(self, now: float) -> int:
        expired = [key for key, entry in self._items.items() if entry.expires <= now]
        for key in expired:
            self._bytes -= self._items.pop(key).size
        return len(expired)

    def clear(self) -> int:
        with self._lock:
            count = len(self._items)
            self._items.clear()
            self._bytes = 0
            return count

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._items)

    @property
    def bytes_used(self) -> int:
        with self._lock:
            return self._bytes
