import os
import hashlib
from time import time
from typing import Optional, Dict, Any
from collections import OrderedDict
import threading
from src.config import CACHE_DIR, CACHE_TTL, REDIS_URL, RATE_LIMIT_STORAGE_URI
from src.logger import get_logger

logger = get_logger("cache")

# Ensure cache directory exists for disk cache fallback
os.makedirs(CACHE_DIR, exist_ok=True)

CACHE_VERSION = "v5"  # bump this if response format changes

# Fast JSON parser (orjson is ~5-10x faster than stdlib json)
try:
    import orjson
    def _json_dumps(obj: Any) -> str:
        return orjson.dumps(obj).decode("utf-8")
    def _json_loads(data: str | bytes) -> Any:
        return orjson.loads(data)
except ImportError:
    import json
    def _json_dumps(obj: Any) -> str:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    def _json_loads(data: str | bytes) -> Any:
        return json.loads(data)


# ── L1: In-Memory Bounded LRU Cache ───────────────────────────────────────────
class _MemoryLRUCache:
    """Thread-safe bounded in-memory LRU cache with TTL expiration."""
    def __init__(self, capacity: int = 1000):
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

    def clear(self):
        with self._lock:
            self._cache.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._cache)


_MEMORY_CACHE = _MemoryLRUCache(capacity=2000)


# ── L2: Redis Client Singleton ───────────────────────────────────────────────
_REDIS_CLIENT = None
_REDIS_INITIALIZED = False
_REDIS_LOCK = threading.Lock()

def get_redis_client():
    """Lazily initialize and return Redis client if configured and available."""
    global _REDIS_CLIENT, _REDIS_INITIALIZED
    if _REDIS_INITIALIZED:
        return _REDIS_CLIENT

    with _REDIS_LOCK:
        if _REDIS_INITIALIZED:
            return _REDIS_CLIENT

        target_url = REDIS_URL or (RATE_LIMIT_STORAGE_URI if str(RATE_LIMIT_STORAGE_URI).startswith("redis") else "")
        if not target_url:
            _REDIS_INITIALIZED = True
            _REDIS_CLIENT = None
            return None

        try:
            import redis
            client = redis.from_url(
                target_url,
                decode_responses=True,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
                health_check_interval=30,
            )
            # Test ping
            client.ping()
            _REDIS_CLIENT = client
            logger.info("Redis L2 cache connected successfully")
        except Exception as e:
            logger.warning(f"Redis cache initialization failed, falling back to disk/memory cache: {e}")
            _REDIS_CLIENT = None

        _REDIS_INITIALIZED = True
        return _REDIS_CLIENT


def make_cache_key(
    artist: str,
    song: str,
    timestamps: bool,
    sequence: Optional[str],
    fast: bool,
    mood: bool,
    metadata: bool,
    translate: bool = False,
    romanize: bool = False,
    language: str = "en",
    word_level: bool = False,
    syllabus: bool = False,
) -> str:
    """Collision-safe, filesystem-safe, and Redis-safe cache key."""
    payload = {
        "v": CACHE_VERSION,
        "artist": (artist or "").strip().lower(),
        "song": (song or "").strip().lower(),
        "timestamps": bool(timestamps),
        "sequence": sequence or "",
        "fast": bool(fast),
        "mood": bool(mood),
        "metadata": bool(metadata),
        "translate": bool(translate),
        "romanize": bool(romanize),
        "language": (language or "en").strip().lower(),
        "word_level": bool(word_level),
        "syllabus": bool(syllabus),
    }

    raw = _json_dumps(payload)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _get_cache_path(key: str) -> str:
    return os.path.join(CACHE_DIR, f"{key}.json")


def load_from_cache(key: str):
    """
    Multi-tier cache loader:
    1. Check L1 Memory LRU
    2. Check L2 Redis (if configured)
    3. Check L3 Disk Cache
    """
    # 1. Check L1 Memory Cache (microsecond response)
    mem_val = _MEMORY_CACHE.get(key)
    if mem_val is not None:
        return mem_val

    # 2. Check L2 Redis Cache
    redis_cli = get_redis_client()
    if redis_cli is not None:
        try:
            val = redis_cli.get(f"lyrica:lyrics:{key}")
            if val:
                data = _json_loads(val)
                result = data.get("result") if isinstance(data, dict) and "result" in data else data
                # Populate L1 cache
                _MEMORY_CACHE.set(key, result, ttl=min(CACHE_TTL, 3600))
                return result
        except Exception as e:
            logger.debug(f"Redis get failed for {key[:12]}: {e}")

    # 3. Check L3 Disk Cache
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
        # Populate L1 cache
        _MEMORY_CACHE.set(key, result, ttl=min(CACHE_TTL, 3600))
        return result

    except Exception:
        try:
            os.remove(path)
        except Exception:
            pass
        return None


def save_to_cache(key: str, result):
    """
    Multi-tier cache saver:
    1. Set in L1 Memory LRU
    2. Set in L2 Redis (with TTL)
    3. Set in L3 Disk Cache
    """
    # 1. Set L1 Memory Cache
    _MEMORY_CACHE.set(key, result, ttl=CACHE_TTL)

    # 2. Set L2 Redis Cache
    redis_cli = get_redis_client()
    if redis_cli is not None:
        try:
            payload = _json_dumps({"result": result, "expiry": time() + CACHE_TTL})
            redis_cli.setex(f"lyrica:lyrics:{key}", CACHE_TTL, payload)
        except Exception as e:
            logger.debug(f"Redis setex failed for {key[:12]}: {e}")

    # 3. Set L3 Disk Cache
    path = _get_cache_path(key)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(_json_dumps({
                "expiry": time() + CACHE_TTL,
                "result": result,
            }))
    except Exception:
        pass


def clear_cache():
    """Clear L1 memory, L2 Redis, and L3 disk caches."""
    _MEMORY_CACHE.clear()
    redis_cleared = 0

    redis_cli = get_redis_client()
    if redis_cli is not None:
        try:
            keys = redis_cli.keys("lyrica:*")
            if keys:
                redis_cleared = redis_cli.delete(*keys)
        except Exception as e:
            logger.warning(f"Redis cache clear failed: {e}")

    removed, failed = [], []
    for fname in os.listdir(CACHE_DIR):
        path = os.path.join(CACHE_DIR, fname)
        if os.path.isfile(path):
            try:
                os.remove(path)
                removed.append(fname)
            except Exception as e:
                failed.append({"file": fname, "error": str(e)})

    return {
        "removed": removed,
        "failed": failed,
        "redis_keys_cleared": redis_cleared,
        "memory_cleared": True
    }


def cache_stats() -> Dict[str, Any]:
    """Return comprehensive multi-tier cache statistics."""
    try:
        disk_files = [f for f in os.listdir(CACHE_DIR) if os.path.isfile(os.path.join(CACHE_DIR, f))]
    except Exception:
        disk_files = []

    redis_info = {"connected": False, "keys": 0}
    redis_cli = get_redis_client()
    if redis_cli is not None:
        try:
            keys_count = len(redis_cli.keys("lyrica:lyrics:*"))
            redis_info = {"connected": True, "lyrics_keys": keys_count}
        except Exception as e:
            redis_info = {"connected": False, "error": str(e)}

    return {
        "backend": "redis+memory+disk" if redis_info["connected"] else "memory+disk",
        "memory_l1_items": _MEMORY_CACHE.size(),
        "redis_l2": redis_info,
        "disk_l3_files": len(disk_files),
        "cache_files": len(disk_files),
        "cache_dir": CACHE_DIR,
        "ttl_seconds": CACHE_TTL,
        "version": CACHE_VERSION,
    }
