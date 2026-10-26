import httpx
import asyncio
import logging
import re
import threading
import weakref
from datetime import datetime, timezone

logger = logging.getLogger("base_fetcher")

# --------------------------------------------------------------------------- #
# Shared async HTTP client — one client per event loop.
#
# A single process-wide AsyncClient cannot safely be shared across event loops:
# httpx/anyio primitives are bound to the loop that first uses them, and the
# Flask sync→async bridge reuses one loop per worker thread. Keying the pool by
# loop keeps connection reuse without "Event loop is closed" / "Future attached
# to a different loop" failures under concurrency.
# --------------------------------------------------------------------------- #
_CLIENTS: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, httpx.AsyncClient]" = weakref.WeakKeyDictionary()
_CLIENT_LOCK = threading.Lock()


def get_http_client() -> httpx.AsyncClient:
    loop = asyncio.get_running_loop()
    with _CLIENT_LOCK:
        client = _CLIENTS.get(loop)
        if client is None or client.is_closed:
            client = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=3.0),
                limits=httpx.Limits(max_connections=200, max_keepalive_connections=50, keepalive_expiry=30.0),
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "Accept-Language": "en-US,en;q=0.9",
                },
                follow_redirects=True,
            )
            _CLIENTS[loop] = client
        return client



def build_result(
    source: str,
    artist: str,
    title: str,
    lyrics: str | None = None,
    timed_lyrics: list | None = None,
    has_timestamps: bool = False,
    **extra,
) -> dict:
    """
    Canonical response shape for every fetcher.
    Centralising this prevents subtle key-name differences from
    breaking the validator / sentiment analyser downstream.
    """
    result = {
        "source": source,
        "artist": artist,
        "title": title,
        "lyrics": lyrics,
        "hasTimestamps": has_timestamps,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    }
    if timed_lyrics:
        result["timed_lyrics"] = timed_lyrics
        result["hasTimestamps"] = True
    result.update(extra)
    return result


# --------------------------------------------------------------------------- #
# Shared LRC parser — used by LRCLIB and SimpMusic
# --------------------------------------------------------------------------- #
_LRC_RE = re.compile(r"\[(\d{2}:\d{2}\.?\d{0,3})\](.*)")

def parse_lrc(lrc_text: str, total_duration_ms: int | None = None) -> list:
    """Parse LRC-format timestamped lyrics into a list of timed line dicts."""
    lines = lrc_text.splitlines()
    parsed = []
    for line in lines:
        m = _LRC_RE.match(line)
        if not m:
            continue
        time_str, text = m.group(1), m.group(2).strip()
        time_str = time_str.replace("..", ".")
        try:
            mins, secs = time_str.split(":")
            start_ms = int((int(mins) * 60 + float(secs)) * 1000)
        except ValueError:
            continue
        if text:
            parsed.append({"text": text, "start_time": start_ms, "end_time": None})

    # Fill end_times from next line's start
    for i, entry in enumerate(parsed):
        if i + 1 < len(parsed):
            entry["end_time"] = parsed[i + 1]["start_time"]
        else:
            entry["end_time"] = (
                total_duration_ms if total_duration_ms
                else entry["start_time"] + 4000
            )
        entry["id"] = f"lrc_{i}"

    return parsed


# --------------------------------------------------------------------------- #
# Base class
# --------------------------------------------------------------------------- #
class BaseFetcher:
    """
    Abstract base fetcher.

    Subclasses implement `fetch(artist, song, timestamps)` and should:
      - Use `get_http_client()` for all HTTP calls (async).
      - Return `build_result(...)` so the shape is always consistent.
      - Catch and log their own exceptions, returning None on failure.
    """

    source_name: str = "unknown"

    def fetch(self, artist: str, song: str, timestamps: bool = False):
        """Override in subclass. May be sync or async."""
        raise NotImplementedError
