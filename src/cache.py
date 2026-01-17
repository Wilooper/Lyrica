import os
import json
import hashlib
from time import time
from typing import Optional
from src.config import CACHE_DIR, CACHE_TTL

# Ensure cache directory exists
os.makedirs(CACHE_DIR, exist_ok=True)

CACHE_VERSION = "v2"  # bump this if response format changes


def make_cache_key(
    artist: str,
    song: str,
    timestamps: bool,
    sequence: Optional[str],
    fast: bool,
    mood: bool,
    metadata: bool
) -> str:
    """
    Collision-safe, filesystem-safe cache key
    """

    payload = {
        "v": CACHE_VERSION,
        "artist": (artist or "").strip().lower(),
        "song": (song or "").strip().lower(),
        "timestamps": bool(timestamps),
        "sequence": sequence or "",
        "fast": bool(fast),
        "mood": bool(mood),
        "metadata": bool(metadata),
    }

    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _get_cache_path(key: str) -> str:
    return os.path.join(CACHE_DIR, f"{key}.json")


def load_from_cache(key: str):
    path = _get_cache_path(key)
    if not os.path.exists(path):
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if time() > data.get("expiry", 0):
            try:
                os.remove(path)
            except Exception:
                pass
            return None

        return data.get("result")

    except Exception:
        # corrupted cache entry → delete
        try:
            os.remove(path)
        except Exception:
            pass
        return None


def save_to_cache(key: str, result):
    path = _get_cache_path(key)

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "expiry": time() + CACHE_TTL,
                    "result": result,
                },
                f,
                ensure_ascii=False,
                separators=(",", ":")
            )
    except Exception:
        pass


def clear_cache():
    removed, failed = [], []

    for fname in os.listdir(CACHE_DIR):
        path = os.path.join(CACHE_DIR, fname)
        try:
            os.remove(path)
            removed.append(fname)
        except Exception as e:
            failed.append({"file": fname, "error": str(e)})

    return {"removed": removed, "failed": failed}


def cache_stats():
    files = os.listdir(CACHE_DIR)
    return {
        "cache_dir": CACHE_DIR,
        "cache_files": len(files),
        "files": files,
        "ttl_seconds": CACHE_TTL,
        "version": CACHE_VERSION
    }
