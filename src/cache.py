import os
import hashlib
import tempfile
from time import time
from typing import Optional, Dict, Any, Iterable
from collections import OrderedDict
import threading
from src.config import CACHE_DIR, CACHE_TTL, REDIS_URL, RATE_LIMIT_STORAGE_URI
from src.logger import get_logger

logger = get_logger("cache")

# Ensure cache directory exists for disk cache fallback
os.makedirs(CACHE_DIR, exist_ok=True)

CACHE_VERSION = "v5"  # bump this if response format changes

# Resolved once at import time — getenv() in cache hot paths is measurable
# under high request rates and makes TTLs inconsistent mid-request.
_IS_PRODUCTION = os.getenv("LYRICA_ENV", "").lower() == "production"
_L1_TTL = min(CACHE_TTL, 43200) if _IS_PRODUCTION else min(CACHE_TTL, 3600)
_REDIS_SCAN_BATCH = 500
_REDIS_KEY_PREFIX = "lyrica:lyrics:"

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


def _atomic_write(path: str, payload: str) -> None:
    """Write a cache file atomically.

    Disk cache writes previously truncated the destination file in place, so a
    crash or two concurrent writers could leave a permanently corrupt JSON file.
    ``os.replace`` is atomic on POSIX and NTFS.
    """
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".lyrica-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                # fsync is not available on every filesystem (e.g. some tmpfs)
                pass
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _scan_redis_keys(client, pattern: str) -> Iterable[str]:
    """Yield Redis keys using SCAN instead of the blocking KEYS command."""
    scan_iter = getattr(client, "scan_iter", None)
    if scan_iter is not None:
        yield from scan_iter(match=pattern, count=_REDIS_SCAN_BATCH)
        return
    # Very old / fake clients may not implement scan_iter.
    for key in client.keys(pattern):
        yield key


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


# Production mode: larger L1 cache for more aggressive in-memory caching
_L1_CAPACITY = 5000 if os.getenv("LYRICA_ENV", "").lower() == "production" else 2000
_MEMORY_CACHE = _MemoryLRUCache(capacity=_L1_CAPACITY)


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
    # ``sequence`` arrives as a query string or as a list from .lyrica.config.
    # Normalise both forms to the same key or the same request is cached twice.
    if isinstance(sequence, (list, tuple)):
        sequence = ",".join(str(part) for part in sequence)
    # Collapse whitespace so "The  Beatles " and "the beatles" share a key.
    artist_norm = " ".join((artist or "").split()).lower()
    song_norm = " ".join((song or "").split()).lower()

    payload = {
        "v": CACHE_VERSION,
        "artist": artist_norm,
        "song": song_norm,
        "timestamps": bool(timestamps),
        "sequence": (sequence or "").strip().lower(),
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
            val = redis_cli.get(f"{_REDIS_KEY_PREFIX}{key}")
            if val:
                data = _json_loads(val)
                result = data.get("result") if isinstance(data, dict) and "result" in data else data
                # Populate L1 cache (longer L1 TTL in production — lyrics are immutable)
                _MEMORY_CACHE.set(key, result, ttl=_L1_TTL)
                return result
        except Exception as e:
            logger.debug(f"Redis get failed for {key[:12]}: {e}")

    # 3. Check L3 Disk Cache
    path = _get_cache_path(key)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = _json_loads(f.read())
    except FileNotFoundError:
        return None
    except Exception:
        try:
            os.remove(path)
        except OSError:
            pass
        return None

    try:
        if time() > data.get("expiry", 0):
            try:
                os.remove(path)
            except OSError:
                pass
            return None

        result = data.get("result")
        _MEMORY_CACHE.set(key, result, ttl=_L1_TTL)
        return result
    except Exception:
        try:
            os.remove(path)
        except OSError:
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
            redis_cli.setex(f"{_REDIS_KEY_PREFIX}{key}", CACHE_TTL, payload)
        except Exception as e:
            logger.debug(f"Redis setex failed for {key[:12]}: {e}")

    # 3. Set L3 Disk Cache
    path = _get_cache_path(key)
    try:
        _atomic_write(path, _json_dumps({
            "expiry": time() + CACHE_TTL,
            "result": result,
        }))
    except Exception as e:
        # Disk full / read-only filesystem should never break a successful
        # request — Redis and memory tiers still hold the value.
        logger.debug(f"Disk cache write failed for {key[:12]}: {e}")


def clear_cache():
    """Clear L1 memory, L2 Redis, and L3 disk caches."""
    _MEMORY_CACHE.clear()
    redis_cleared = 0

    redis_cli = get_redis_client()
    if redis_cli is not None:
        try:
            # SCAN in small batches instead of KEYS: KEYS blocks Redis for the
            # whole keyspace and is unsafe on a shared production instance.
            batch = []
            for redis_key in _scan_redis_keys(redis_cli, "lyrica:*"):
                batch.append(redis_key)
                if len(batch) >= _REDIS_SCAN_BATCH:
                    redis_cleared += redis_cli.delete(*batch)
                    batch.clear()
            if batch:
                redis_cleared += redis_cli.delete(*batch)
        except Exception as e:
            logger.warning(f"Redis cache clear failed: {e}")

    removed, failed = [], []
    try:
        cache_entries = os.listdir(CACHE_DIR)
    except OSError as e:
        logger.warning(f"Cache directory listing failed: {e}")
        cache_entries = []
    for fname in cache_entries:
        path = os.path.join(CACHE_DIR, fname)
        if os.path.isfile(path):
            try:
                os.remove(path)
                removed.append(fname)
            except OSError as e:
                failed.append({"file": fname, "error": str(e)})

    # Process-local auxiliary caches share the same lifecycle as the lyrics
    # cache. Imported lazily to avoid a circular import at module load time.
    translation_result = {}
    metadata_cleared = 0
    try:
        from src.translation_cache import clear_translation_cache
        translation_result = clear_translation_cache()
    except Exception as e:
        logger.warning(f"Translation cache clear failed: {e}")
    try:
        from src.metadata_extractor import clear_metadata_cache
        metadata_cleared = clear_metadata_cache()
    except Exception as e:
        logger.warning(f"Metadata cache clear failed: {e}")

    return {
        "removed": removed,
        "failed": failed,
        "redis_keys_cleared": redis_cleared,
        "memory_cleared": True,
        "translation_cache": translation_result,
        "metadata_items_cleared": metadata_cleared,
    }


def cache_stats() -> Dict[str, Any]:
    """Return comprehensive multi-tier cache statistics."""
    try:
        disk_files = [f for f in os.listdir(CACHE_DIR) if os.path.isfile(os.path.join(CACHE_DIR, f))]
    except OSError:
        disk_files = []

    redis_info = {"connected": False, "keys": 0}
    redis_cli = get_redis_client()
    if redis_cli is not None:
        try:
            # DBSIZE is O(1). Scanning the whole keyspace (or KEYS) from a
            # public stats endpoint is an avoidable DoS amplifier.
            dbsize = getattr(redis_cli, "dbsize", None)
            if dbsize is not None:
                keys_count = int(dbsize())
            else:  # very old / fake clients
                keys_count = sum(1 for _ in _scan_redis_keys(redis_cli, f"{_REDIS_KEY_PREFIX}*"))
            redis_info = {"connected": True, "keys": keys_count}
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
