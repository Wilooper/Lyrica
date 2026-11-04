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
# Shared LRC parser — used by LRCLIB, NetEase, Megalobiz, Musixmatch, SimpMusic
# --------------------------------------------------------------------------- #
# Matches one timestamp tag: [mm:ss], [mm:ss.xxx], [mm:ss:xx], [hh:mm:ss.xxx]
_LRC_TAG_RE = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
_LRC_OFFSET_RE = re.compile(r"\[offset:\s*([+-]?\d+)\]", re.IGNORECASE)
_LRC_META_RE = re.compile(r"^\[(?:ar|ti|al|by|length|re|ve|offset):.*\]$", re.IGNORECASE)


def _tag_to_ms(minutes: str, seconds: str, fraction: str | None) -> int | None:
    try:
        mins = int(minutes)
        secs = int(seconds)
    except ValueError:
        return None
    if secs > 59:
        return None
    ms = mins * 60_000 + secs * 1_000
    if fraction:
        ms += int(fraction.ljust(3, "0")[:3])
    return ms


def parse_lrc(lrc_text: str, total_duration_ms: int | None = None) -> list:
    """Parse LRC-format timestamped lyrics into timed line dicts.

    Handles multiple timestamps on one line (``[00:10.00][01:20.00] chorus``),
    metadata tags, and ``[offset:...]``. Output is sorted by start time so the
    verifier's monotonicity check is meaningful.
    """
    if not lrc_text:
        return []

    offset_match = _LRC_OFFSET_RE.search(lrc_text)
    offset_ms = int(offset_match.group(1)) if offset_match else 0

    parsed: list[dict] = []
    seen: set[tuple[int, str]] = set()

    for raw_line in lrc_text.splitlines():
        line = raw_line.strip()
        if not line or _LRC_META_RE.match(line):
            continue
        tags = list(_LRC_TAG_RE.finditer(line))
        if not tags:
            continue
        text = _LRC_TAG_RE.sub("", line).strip()
        if not text:
            continue
        for tag in tags:
            start_ms = _tag_to_ms(tag.group(1), tag.group(2), tag.group(3))
            if start_ms is None:
                continue
            start_ms = max(0, start_ms + offset_ms)
            key = (start_ms, text)
            if key in seen:
                continue
            seen.add(key)
            parsed.append({"text": text, "start_time": start_ms, "end_time": None})

    parsed.sort(key=lambda entry: entry["start_time"])

    # Fill end_times from the next line's start (never a zero-length span).
    for i, entry in enumerate(parsed):
        if i + 1 < len(parsed) and parsed[i + 1]["start_time"] > entry["start_time"]:
            entry["end_time"] = parsed[i + 1]["start_time"]
        elif total_duration_ms and total_duration_ms > entry["start_time"]:
            entry["end_time"] = total_duration_ms
        else:
            entry["end_time"] = entry["start_time"] + 4000
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
