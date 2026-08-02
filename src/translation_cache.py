"""
src/translation_cache.py

Separate file-based cache for lyrics translations and romanizations.

Keyed differently from the main lyrics cache since the same lyrics
can be translated into many different languages. Cache files are stored
in a subdirectory of the main cache dir: cache_data/translations/

Future-ready: The `cached_from` field in responses returns "local_cache"
or "fresh" — community DB hookpoint for later.
"""

from __future__ import annotations

import hashlib
import json
import os
from time import time
from typing import Optional

from src.config import CACHE_DIR, CACHE_TTL
from src.logger import get_logger

logger = get_logger("translation_cache")

# Translation cache lives in a subdirectory
_TRANSLATION_CACHE_DIR = os.path.join(CACHE_DIR, "translations")
os.makedirs(_TRANSLATION_CACHE_DIR, exist_ok=True)

_CACHE_VERSION = "t_v1"  # Bump when translation response format changes


def make_translation_cache_key(
    artist: str,
    song: str,
    source: str,
    language: str,
    translate: bool,
    romanize: bool,
    has_timestamps: bool,
) -> str:
    """
    Generate a collision-safe, filesystem-safe cache key for translations.

    Includes source and timestamps because different sources may return
    different lyrics text for the same song.
    """
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

    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _get_cache_path(key: str) -> str:
    """Get the filesystem path for a cache key."""
    return os.path.join(_TRANSLATION_CACHE_DIR, f"{key}.json")


def load_translation_cache(key: str) -> Optional[dict]:
    """
    Load a translation result from cache.

    Returns the cached result dict or None if not found / expired.
    """
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

        logger.info(f"Translation cache hit: {key[:12]}...")
        return data.get("result")

    except Exception:
        # Corrupted cache entry — delete
        try:
            os.remove(path)
        except Exception:
            pass
        return None


def save_translation_cache(key: str, result: dict):
    """
    Save a translation result to cache.

    Args:
        key: Cache key from make_translation_cache_key()
        result: The translation result dict to cache
    """
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
                separators=(",", ":"),
            )
        logger.info(f"Translation cached: {key[:12]}...")
    except Exception as e:
        logger.warning(f"Translation cache save failed: {e}")


def translation_cache_stats() -> dict:
    """Return translation cache statistics."""
    try:
        files = os.listdir(_TRANSLATION_CACHE_DIR)
    except FileNotFoundError:
        files = []

    return {
        "cache_dir": _TRANSLATION_CACHE_DIR,
        "cache_files": len(files),
        "ttl_seconds": CACHE_TTL,
        "version": _CACHE_VERSION,
    }
