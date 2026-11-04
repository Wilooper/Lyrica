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

CACHE_VERSION = "v6"  # bump this if response format or stored shape changes

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
    pass_param: bool = False,
) -> str:
    """Backwards-compatible alias for the per-view key.

    New code should call :func:`make_view_cache_key` explicitly and use
    :func:`make_lyrics_cache_key` for the shared raw entry.
    """
    return make_view_cache_key(
        artist,
        song,
        timestamps=timestamps,
        sequence=sequence,
        mood=mood,
        metadata=metadata,
        translate=translate,
        romanize=romanize,
        language=language,
        word_level=word_level,
        syllabus=syllabus,
        pass_param=pass_param,
    )


def _hash_payload(payload: dict) -> str:
    raw = _json_dumps(payload)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def make_lyrics_cache_key(
    artist: str,
    song: str,
    sequence=None,
    pass_param: bool = False,
) -> str:
    """Canonical key for the raw (richest-tier) lyrics entry.

    Flags such as ``fast``, ``mood``, ``metadata``, ``translate``, and the sync
    booleans are deliberately excluded: they are views of the same song, not
    different songs.
    """
    from src.core.normalizer import normalize_identity, normalize_sequence

    artist_norm, song_norm = normalize_identity(artist, song)
    return _hash_payload({
        "v": CACHE_VERSION,
        "kind": "raw",
        "artist": artist_norm,
        "song": song_norm,
        "sequence": normalize_sequence(sequence),
        "pass": bool(pass_param),
    })


def make_view_cache_key(
    artist: str,
    song: str,
    timestamps: bool = False,
    sequence=None,
    mood: bool = False,
    metadata: bool = False,
    translate: bool = False,
    romanize: bool = False,
    language: str = "en",
    word_level: bool = False,
    syllabus: bool = False,
    pass_param: bool = False,
    extra: Optional[dict] = None,
) -> str:
    """Key for a fully rendered response (enrichments included).

    ``fast`` is excluded because it changes latency, not content.
    """
    from src.core.normalizer import normalize_identity, normalize_sequence

    artist_norm, song_norm = normalize_identity(artist, song)
    payload = {
        "v": CACHE_VERSION,
        "kind": "view",
        "artist": artist_norm,
        "song": song_norm,
        "sequence": normalize_sequence(sequence),
        "pass": bool(pass_param),
        "timestamps": bool(timestamps),
        "mood": bool(mood),
        "metadata": bool(metadata),
        "translate": bool(translate),
        "romanize": bool(romanize),
        "language": (language or "en").strip().lower(),
        "word_level": bool(word_level),
        "syllabus": bool(syllabus),
    }
    if extra:
        payload.update(extra)
    return _hash_payload(payload)



def _get_cache_path(key: str) -> str:
    return os.path.join(CACHE_DIR, f"{key}.json")


def _normalize_record(data) -> dict:
    """Accept old ``{"result": ...}`` files and new record dicts."""
    if isinstance(data, dict) and ("result" in data or "body" in data or "tier" in data):
        return {
            "result": data.get("result"),
            "tier": data.get("tier"),
            "body": data.get("body"),
        }
    return {"result": data, "tier": None, "body": None}


def _load_record(key: str) -> Optional[dict]:
    """Multi-tier record loader: L1 memory -> L2 Redis -> L3 disk."""
    # 1. L1 memory (microsecond response)
    mem_val = _MEMORY_CACHE.get(key)
    if mem_val is not None:
        return mem_val

    # 2. L2 Redis
    redis_cli = get_redis_client()
    if redis_cli is not None:
        try:
            val = redis_cli.get(f"{_REDIS_KEY_PREFIX}{key}")
            if val:
                record = _normalize_record(_json_loads(val))
                _MEMORY_CACHE.set(key, record, ttl=_L1_TTL)
                return record
        except Exception as e:
            logger.debug(f"Redis get failed for {key[:12]}: {e}")

    # 3. L3 disk
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

        record = _normalize_record(data)
        _MEMORY_CACHE.set(key, record, ttl=_L1_TTL)
        return record
    except Exception:
        try:
            os.remove(path)
        except OSError:
            pass
        return None


def _save_record(key: str, record: dict, ttl: int) -> None:
    """Write one record to every configured tier."""
    # L1 uses one TTL policy everywhere (previously save used CACHE_TTL while
    # Redis/disk promotion used the shorter _L1_TTL).
    _MEMORY_CACHE.set(key, record, ttl=min(ttl, _L1_TTL))

    redis_cli = get_redis_client()
    if redis_cli is not None:
        try:
            payload = _json_dumps({**record, "expiry": time() + ttl})
            redis_cli.setex(f"{_REDIS_KEY_PREFIX}{key}", ttl, payload)
        except Exception as e:
            logger.debug(f"Redis setex failed for {key[:12]}: {e}")

    path = _get_cache_path(key)
    try:
        _atomic_write(path, _json_dumps({**record, "expiry": time() + ttl}))
    except Exception as e:
        # Disk full / read-only filesystem should never break a successful
        # request — Redis and memory tiers still hold the value.
        logger.debug(f"Disk cache write failed for {key[:12]}: {e}")


def load_from_cache(key: str):
    record = _load_record(key)
    return record.get("result") if record else None


def save_to_cache(key: str, result):
    _save_record(key, {"result": result}, CACHE_TTL)


def load_raw(key: str):
    """Return ``(raw_result, tier)`` or ``None``."""
    record = _load_record(key)
    if not record:
        return None
    result = record.get("result")
    if result is None:
        return None
    return result, (record.get("tier") or "plain")


def save_raw(key: str, result, tier: str = "plain"):
    _save_record(key, {"result": result, "tier": tier}, CACHE_TTL)


def load_view(key: str):
    """Return ``(result, serialized_body)`` or ``None``.

    The body is stored so a cache hit can skip JSON encoding entirely.
    """
    record = _load_record(key)
    if not record or record.get("result") is None:
        return None
    body = record.get("body")
    if not body:
        body = _json_dumps(record["result"])
        record["body"] = body
    return record["result"], body


def save_view(key: str, result, body: Optional[str] = None):
    if body is None:
        body = _json_dumps(result)
    _save_record(key, {"result": result, "body": body}, CACHE_TTL)



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
    negative_cleared = 0
    try:
        from src.core.negative_cache import negative_cache
        negative_cleared = negative_cache.clear()
    except Exception as e:
        logger.warning(f"Negative cache clear failed: {e}")
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
        "negative_items_cleared": negative_cleared,
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

    try:
        from src.core.negative_cache import negative_cache
        negative = negative_cache.stats()
    except Exception:
        negative = {}

    return {
        "backend": "redis+memory+disk" if redis_info["connected"] else "memory+disk",
        "memory_l1_items": _MEMORY_CACHE.size(),
        "redis_l2": redis_info,
        "disk_l3_files": len(disk_files),
        "cache_files": len(disk_files),
        "cache_dir": CACHE_DIR,
        "ttl_seconds": CACHE_TTL,
        "version": CACHE_VERSION,
        "negative": negative,
    }
