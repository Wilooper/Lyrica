"""Short-TTL negative cache for confirmed "not found" songs.

Only write an entry when at least one provider definitively answered "no such
song" and no provider errored. Provider errors are never cached as absence: a
timeout must not hide a song for an hour.
"""

from __future__ import annotations

import os
import threading
import time

from src.logger import get_logger

logger = get_logger("negative_cache")

_TTL = max(60, int(os.getenv("LYRICA_NEGATIVE_TTL", "3600")))
_MAX_ENTRIES = max(100, int(os.getenv("LYRICA_NEGATIVE_MAX", "5000")))
_PREFIX = "lyrica:neg:"


class _NegativeCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[float, str]] = {}
        self._hits = 0
        self._writes = 0

    def _evict_locked(self, now: float) -> None:
        if len(self._entries) <= _MAX_ENTRIES:
            return
        expired = [key for key, (expiry, _) in self._entries.items() if expiry <= now]
        for key in expired:
            self._entries.pop(key, None)
        while len(self._entries) > _MAX_ENTRIES:
            self._entries.pop(next(iter(self._entries)))

    def get(self, key: str) -> str | None:
        now = time.time()
        with self._lock:
            entry = self._entries.get(key)
            if entry and entry[0] > now:
                self._hits += 1
                return entry[1] or "not_found"
            if entry:
                self._entries.pop(key, None)

        # Multi-worker deployments can share the miss through Redis.
        try:
            from src.cache import get_redis_client

            client = get_redis_client()
            if client is not None:
                value = client.get(f"{_PREFIX}{key}")
                if value:
                    self._hits += 1
                    return value if isinstance(value, str) else value.decode("utf-8", "ignore")
        except Exception as exc:  # pragma: no cover - Redis is optional
            logger.debug("Negative cache Redis read failed: %s", exc)
        return None

    def set(self, key: str, reason: str = "not_found", ttl: int | None = None) -> None:
        expires = time.time() + (ttl or _TTL)
        with self._lock:
            self._entries[key] = (expires, reason)
            self._writes += 1
            self._evict_locked(time.time())

        try:
            from src.cache import get_redis_client

            client = get_redis_client()
            if client is not None:
                client.setex(f"{_PREFIX}{key}", ttl or _TTL, reason)
        except Exception as exc:  # pragma: no cover - Redis is optional
            logger.debug("Negative cache Redis write failed: %s", exc)

    def clear(self) -> int:
        with self._lock:
            count = len(self._entries)
            self._entries.clear()
        try:
            from src.cache import get_redis_client, _scan_redis_keys

            client = get_redis_client()
            if client is not None:
                batch = []
                for redis_key in _scan_redis_keys(client, f"{_PREFIX}*"):
                    batch.append(redis_key)
                    if len(batch) >= 500:
                        client.delete(*batch)
                        batch.clear()
                if batch:
                    client.delete(*batch)
        except Exception as exc:  # pragma: no cover - Redis is optional
            logger.debug("Negative cache Redis clear failed: %s", exc)
        return count

    def stats(self) -> dict:
        now = time.time()
        with self._lock:
            live = sum(1 for expiry, _ in self._entries.values() if expiry > now)
            return {
                "entries": live,
                "hits": self._hits,
                "writes": self._writes,
                "ttl_seconds": _TTL,
            }


negative_cache = _NegativeCache()
