"""
src/translation_cache.py

Multi-tier cache for lyrics translations and romanizations.
Keyed differently from the main lyrics cache since the same lyrics
can be translated into many different languages.

Tiers:
  - L1: In-memory bounded LRU cache for instant hits
  - L2: Redis cache (when configured via REDIS_URL) with native TTL
  - L3: File-based cache in cache_data/translations/
"""

from __future__ import annotations

import hashlib
import os
import threading
from collections import OrderedDict
from time import time
from typing import Optional, Dict, Any

from src.config import CACHE_DIR, CACHE_TTL
from src.cache import get_redis_client, _json_dumps, _json_loads
from src.logger import get_logger

logger = get_logger("translation_cache")

# Translation cache directory for disk tier
_TRANSLATION_CACHE_DIR = os.path.join(CACHE_DIR, "translations")
os.makedirs(_TRANSLATION_CACHE_DIR, exist_ok=True)

_CACHE_VERSION = "t_v2"


# ── L1: In-Memory Bounded LRU Cache ───────────────────────────────────────────
class _TranslationMemoryCache:
    def __init__(self, capacity: int = 500):
        self._capacity = capacity
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._cache:
                return None
            expiry, value = self._cache[key]
            if time() > expiry:
                del self._cache[key]
                return None
            self._cache.move_to_end(key)
            return value

    def set(self, key: str, value: Any, ttl: int):
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = (time() + ttl, value)
            if len(self._cache) > self._capacity:
                self._cache.popitem(last=False)

    def size(self) -> int:
        with self._lock:
            return len(self._cache)


_TRANS_MEM_CACHE = _TranslationMemoryCache(capacity=1000)


def make_translation_cache_key(
    artist: str,
    song: str,
    source: str,
    language: str,
    translate: bool,
    romanize: bool,
    has_timestamps: bool,
) -> str:
    """Generate a collision-safe, filesystem-safe cache key for translations."""
    payload = {
        "v": _CACHE_VERSION,
        "artist": (artist or "").strip().lower(),
        "song": (song or "").strip().lower(),
        "source": (source or "").strip().lower(),
        "language": (language or "en").strip().lower(),
        "translate": bool(translate),
        "romanize": bool(romanize),
        "has_timestamps": bool(has_timestamps),
    }

    raw = _json_dumps(payload)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _get_cache_path(key: str) -> str:
    """Get the filesystem path for a cache key."""
    return os.path.join(_TRANSLATION_CACHE_DIR, f"{key}.json")


def load_translation_cache(key: str) -> Optional[dict]:
    """
    Multi-tier translation cache loader:
    1. Check L1 In-Memory LRU
    2. Check L2 Redis
    3. Check L3 Disk Cache
    """
    # 1. L1 Memory
    mem_hit = _TRANS_MEM_CACHE.get(key)
    if mem_hit is not None:
        logger.debug(f"Translation L1 memory cache hit: {key[:12]}...")
        return mem_hit

    # 2. L2 Redis
    redis_cli = get_redis_client()
    if redis_cli is not None:
        try:
            val = redis_cli.get(f"lyrica:trans:{key}")
            if val:
                data = _json_loads(val)
                result = data.get("result") if isinstance(data, dict) and "result" in data else data
                _TRANS_MEM_CACHE.set(key, result, ttl=min(CACHE_TTL, 3600))
                logger.info(f"Translation L2 Redis cache hit: {key[:12]}...")
                return result
        except Exception as e:
            logger.debug(f"Translation Redis get failed for {key[:12]}: {e}")

    # 3. L3 Disk
    path = _get_cache_path(key)
    if not os.path.exists(path):
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = _json_loads(f.read())

        if time() > data.get("expiry", 0):
            try:
                os.remove(path)
            except Exception:
                pass
            return None

        result = data.get("result")
        _TRANS_MEM_CACHE.set(key, result, ttl=min(CACHE_TTL, 3600))
        logger.info(f"Translation L3 disk cache hit: {key[:12]}...")
        return result

    except Exception:
        try:
            os.remove(path)
        except Exception:
            pass
        return None


def save_translation_cache(key: str, result: dict):
    """
    Save translation result across all tiers (Memory, Redis, Disk).
    """
    # 1. L1 Memory
    _TRANS_MEM_CACHE.set(key, result, ttl=CACHE_TTL)

    # 2. L2 Redis
    redis_cli = get_redis_client()
    if redis_cli is not None:
        try:
            payload = _json_dumps({"result": result, "expiry": time() + CACHE_TTL})
            redis_cli.setex(f"lyrica:trans:{key}", CACHE_TTL, payload)
        except Exception as e:
            logger.debug(f"Translation Redis save failed for {key[:12]}: {e}")

    # 3. L3 Disk
    path = _get_cache_path(key)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(_json_dumps({
                "expiry": time() + CACHE_TTL,
                "result": result,
            }))
        logger.info(f"Translation saved to disk: {key[:12]}...")
    except Exception as e:
        logger.warning(f"Translation disk cache save failed: {e}")


def translation_cache_stats() -> dict:
    """Return comprehensive translation cache statistics."""
    try:
        files = os.listdir(_TRANSLATION_CACHE_DIR)
    except FileNotFoundError:
        files = []

    redis_info = {"connected": False, "trans_keys": 0}
    redis_cli = get_redis_client()
    if redis_cli is not None:
        try:
            keys_count = len(redis_cli.keys("lyrica:trans:*"))
            redis_info = {"connected": True, "trans_keys": keys_count}
        except Exception as e:
            redis_info = {"connected": False, "error": str(e)}

    return {
        "cache_dir": _TRANSLATION_CACHE_DIR,
        "memory_l1_items": _TRANS_MEM_CACHE.size(),
        "redis_l2": redis_info,
        "disk_l3_files": len(files),
        "ttl_seconds": CACHE_TTL,
        "version": _CACHE_VERSION,
    }
