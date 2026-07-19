"""
src/sources/lrclib_fetcher.py

Fetches synced or plain lyrics from LRCLIB (https://lrclib.net).

Migrated from `requests` (blocking) to `httpx.AsyncClient` for full async
compatibility with the event loop — no more thread-pool overhead or potential
event-loop blocking under high concurrency.

Retry logic: LRCLIB's free server occasionally rejects keep-alive connections.
We handle this with httpx's built-in retry transport.
"""

import re
from datetime import datetime, timezone

import httpx

from src.config import LRCLIB_API_URL
from src.logger import get_logger
from .base_fetcher import BaseFetcher, build_result, parse_lrc

logger = get_logger("lrclib_fetcher")

_LRCLIB_SEARCH = "https://lrclib.net/api/search"
_UA = "Lyrica/1.0 (https://github.com/Wilooper/Lyrica)"


class LRCLIBFetcher(BaseFetcher):
    source_name = "lrclib"

    async def fetch(self, artist: str, song: str, timestamps: bool = True, proxy: str | None = None):
        """
        Fetch lyrics from LRCLIB.

        Args:
            artist:     Artist name
            song:       Song title
            timestamps: If True, prefer synced (LRC) lyrics
            proxy:      Optional proxy URL (http/https/socks5)
        """
        # Build a fresh async client per call — keeps proxy/retry logic clean
        transport = httpx.AsyncHTTPTransport(retries=3)
        client_kwargs = dict(
            transport=transport,
            timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=2.0),
            headers={"User-Agent": _UA},
            follow_redirects=True,
        )
        if proxy:
            client_kwargs["proxy"] = proxy

        async with httpx.AsyncClient(**client_kwargs) as client:
            try:
                logger.info(f"LRCLIB: fetching '{artist} – {song}' (timestamps={timestamps})")

                # ── Step 1: search ───────────────────────────────────────────
                search_resp = await client.get(
                    _LRCLIB_SEARCH,
                    params={"track_name": song, "artist_name": artist},
                )
                if search_resp.status_code != 200:
                    logger.warning(f"LRCLIB search returned {search_resp.status_code}")
                    return None

                results = search_resp.json()
                if not results:
                    logger.info("LRCLIB: no results found")
                    return None

                track = results[0]

                # ── Step 2: fetch full track data ────────────────────────────
                get_resp = await client.get(
                    LRCLIB_API_URL,
                    params={
                        "track_name":  track.get("trackName"),
                        "artist_name": track.get("artistName"),
                        "album_name":  track.get("albumName"),
                        "duration":    track.get("duration"),
                    },
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
                    # Graceful fallback: if synced not available, try plain
                    if timestamps:
                        lyrics = data.get("plainLyrics")
                    if not lyrics:
                        logger.info("LRCLIB: no lyrics content in response")
                        return None

                result = {
                    "source":        "lrclib",
                    "artist":        data.get("artistName"),
                    "title":         data.get("trackName"),
                    "album":         data.get("albumName"),
                    "duration":      data.get("duration"),
                    "instrumental":  data.get("instrumental", False),
                    "lyrics":        lyrics,
                    "hasTimestamps": False,
                    "timestamp":     datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                }

                # ── Step 3: parse synced lyrics ──────────────────────────────
                if timestamps and data.get("syncedLyrics"):
                    timed = parse_lrc(data["syncedLyrics"], data.get("duration"))
                    if timed:
                        result["timed_lyrics"]  = timed
                        result["hasTimestamps"] = True

                logger.info(f"LRCLIB: success (hasTimestamps={result['hasTimestamps']})")
                return result

            except httpx.TimeoutException:
                logger.error("LRCLIB timeout")
                return None
            except httpx.ConnectError as e:
                logger.error(f"LRCLIB connection error: {e}")
                return None
            except Exception as e:
                logger.error(f"LRCLIB error: {e}")
                return None
