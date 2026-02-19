import re
import time
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.config import LRCLIB_API_URL
from src.logger import get_logger
from .base_fetcher import BaseFetcher

logger = get_logger("lrclib_fetcher")


def _make_session() -> requests.Session:
    """
    Create a requests Session with retry logic and connection resilience.

    LRCLIB's free server occasionally drops keep-alive connections mid-request
    ('Server disconnected without sending a response'). We handle this with:
      - Automatic retries on connection errors and 5xx responses
      - Exponential back-off between retries
      - Short per-request timeout so we fail fast and retry quickly
      - A fresh session is created per-request to avoid stale connections
    """
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.4,          # 0s, 0.4s, 0.8s between retries
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://",  adapter)
    return session


class LRCLIBFetcher(BaseFetcher):

    def fetch(self, artist: str, song: str, timestamps: bool = True):
        session = _make_session()
        try:
            logger.info(f"LRCLIB: fetching '{artist} – {song}' (timestamps={timestamps})")

            # ── Step 1: search ───────────────────────────────────────────────
            search_resp = session.get(
                "https://lrclib.net/api/search",
                params={"track_name": song, "artist_name": artist},
                timeout=(5, 15),     # (connect_timeout, read_timeout)
                headers={"User-Agent": "Lyrica/1.0 (music lyrics API)"},
            )
            if search_resp.status_code != 200:
                logger.warning(f"LRCLIB search returned {search_resp.status_code}")
                return None

            results = search_resp.json()
            if not results:
                logger.info("LRCLIB: no results found")
                return None

            track = results[0]

            # ── Step 2: fetch full track data ────────────────────────────────
            get_resp = session.get(
                LRCLIB_API_URL,
                params={
                    "track_name":  track.get("trackName"),
                    "artist_name": track.get("artistName"),
                    "album_name":  track.get("albumName"),
                    "duration":    track.get("duration"),
                },
                timeout=(5, 15),
                headers={"User-Agent": "Lyrica/1.0 (music lyrics API)"},
            )
            if get_resp.status_code != 200:
                logger.warning(f"LRCLIB get returned {get_resp.status_code}")
                return None

            data = get_resp.json()
            lyrics = (
                data.get("syncedLyrics") if timestamps
                else data.get("plainLyrics")
            )
            if not lyrics:
                # If synced lyrics not available, fall back to plain
                if timestamps:
                    lyrics = data.get("plainLyrics")
                if not lyrics:
                    logger.info("LRCLIB: no lyrics content in response")
                    return None

            result = {
                "source":       "lrclib",
                "artist":       data.get("artistName"),
                "title":        data.get("trackName"),
                "album":        data.get("albumName"),
                "duration":     data.get("duration"),
                "instrumental": data.get("instrumental", False),
                "lyrics":       lyrics,
                "hasTimestamps": False,
                "timestamp":    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            }

            # ── Step 3: parse synced lyrics ──────────────────────────────────
            if timestamps and data.get("syncedLyrics"):
                timed = _parse_lrc(data["syncedLyrics"], data.get("duration"))
                if timed:
                    result["timed_lyrics"]  = timed
                    result["hasTimestamps"] = True

            logger.info(f"LRCLIB: success (hasTimestamps={result['hasTimestamps']})")
            return result

        except requests.exceptions.ConnectionError as e:
            # Catches "Server disconnected without sending a response"
            logger.error(f"LRCLIB connection error (will retry via HTTPAdapter): {e}")
            return None
        except requests.exceptions.Timeout:
            logger.error("LRCLIB timeout")
            return None
        except Exception as e:
            logger.error(f"LRCLIB error: {e}")
            return None
        finally:
            session.close()


def _parse_lrc(synced_lyrics: str, duration=None) -> list:
    """Parse LRC-format synced lyrics into a list of timed dicts."""
    timed = []
    lines = synced_lyrics.split("\n")
    pattern = re.compile(r"\[(\d{2}:\d{2}\.?\d{1,3})\](.*)")

    for i, line in enumerate(lines):
        m = pattern.match(line)
        if not m:
            continue
        time_str, text = m.group(1), m.group(2)
        # Normalize timestamps: [01:23.4] → [01:23.40]
        time_str = time_str.replace("..", ".")
        try:
            parts = time_str.split(":")
            minutes = float(parts[0])
            seconds = float(parts[1])
            start_ms = int((minutes * 60 + seconds) * 1000)

            # Determine end time from next line's timestamp
            end_ms = None
            if i + 1 < len(lines):
                nm = pattern.match(lines[i + 1])
                if nm:
                    nt = nm.group(1).replace("..", ".")
                    np = nt.split(":")
                    nm_sec = float(np[0]) * 60 + float(np[1])
                    end_ms = int(nm_sec * 1000)

            if end_ms is None:
                end_ms = (
                    int(duration * 1000) if duration
                    else start_ms + 4000
                )

            if text.strip():
                timed.append({
                    "text":       text.strip(),
                    "start_time": start_ms,
                    "end_time":   end_ms,
                    "id":         f"lrc_{i}",
                })
        except (ValueError, IndexError):
            continue

    return timed
