import os
import json
from time import time
from typing import Optional
from src.config import CACHE_DIR, CACHE_TTL

# Ensure cache directory exists INSIDE project (Render safe)
os.makedirs(CACHE_DIR, exist_ok=True)

def make_cache_key(artist: str, song: str, timestamps: bool, sequence: Optional[str]):
    artist = (artist or "").strip().lower()
    song = (song or "").strip().lower()
    seq = sequence or ""
    return f"{artist}__{song}__ts={int(bool(timestamps))}__seq={seq}".replace(" ", "_")

def get_cache_path(key: str):
    return os.path.join(CACHE_DIR, f"{key}.json")

def load_from_cache(key: str):
    path = get_cache_path(key)
    if not os.path.exists(path):
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if time() > data.get("expiry", 0):
            try:
                os.remove(path)
                print(f"[CACHE] expired removed: {path}")
            except Exception as e:
                print("[CACHE] expiry delete failed:", e)
            return None

        return data.get("result")

    except Exception as e:
        print("[CACHE] read failed:", e)
        return None

def save_to_cache(key: str, result):
    path = get_cache_path(key)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {"result": result, "expiry": time() + CACHE_TTL},
                f,
                ensure_ascii=False,
                indent=2
            )
    except Exception as e:
        print("[CACHE] write failed:", e)

def clear_cache():
    removed = []
    failed = []

    for f in os.listdir(CACHE_DIR):
        path = os.path.join(CACHE_DIR, f)
        try:
            os.remove(path)
            removed.append(f)
        except Exception as e:
            failed.append({"file": f, "error": str(e)})

    print(f"[CACHE] cleared={len(removed)} failed={len(failed)}")
    return {"removed": removed, "failed": failed}

def cache_stats():
    files = os.listdir(CACHE_DIR)
    return {
        "cache_dir": CACHE_DIR,
        "cache_files": len(files),
        "files": files
    }

