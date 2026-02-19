from datetime import datetime, timezone
import httpx
from src.config import LRCLIB_API_URL
from src.logger import get_logger
from .base_fetcher import BaseFetcher, get_http_client, build_result, parse_lrc

logger = get_logger("lrclib_fetcher")

SEARCH_URL = "https://lrclib.net/api/search"


class LRCLIBFetcher(BaseFetcher):
    source_name = "lrclib"

    async def fetch(self, artist: str, song: str, timestamps: bool = True):
        """
        Two-step LRCLIB fetch:
          1. Search to find the best matching track (with album/duration metadata).
          2. GET /api/get with those exact params for the synced/plain lyrics.

        Both calls reuse the shared async httpx client — no new TCP handshakes.
        """
        client = get_http_client()
        try:
            logger.info(f"Attempting LRCLIB for {artist} - {song}")

            # Step 1: search
            search_resp = await client.get(
                SEARCH_URL,
                params={"track_name": song, "artist_name": artist},
            )
            if search_resp.status_code != 200:
                logger.warning(f"LRCLIB search returned {search_resp.status_code}")
                return None

            results = search_resp.json()
            if not results:
                return None

            track = results[0]

            # Step 2: get exact lyrics
            get_resp = await client.get(
                LRCLIB_API_URL,
                params={
                    "track_name": track.get("trackName"),
                    "artist_name": track.get("artistName"),
                    "album_name":  track.get("albumName"),
                    "duration":    track.get("duration"),
                },
            )
            if get_resp.status_code != 200:
                return None

            data = get_resp.json()

            # Pick the right lyric field
            raw_lyrics = (
                data.get("syncedLyrics") if timestamps else data.get("plainLyrics")
            )
            # Fallback: if synced was requested but unavailable, try plain
            if not raw_lyrics and timestamps:
                raw_lyrics = data.get("plainLyrics")

            if not raw_lyrics:
                return None

            duration_ms = int(data.get("duration", 0) * 1000) or None
            timed = None
            if timestamps and data.get("syncedLyrics"):
                timed = parse_lrc(data["syncedLyrics"], total_duration_ms=duration_ms)

            return build_result(
                source="lrclib",
                artist=data.get("artistName", artist),
                title=data.get("trackName", song),
                lyrics=raw_lyrics,
                timed_lyrics=timed,
                has_timestamps=bool(timed),
                album=data.get("albumName"),
                duration=data.get("duration"),
                instrumental=data.get("instrumental", False),
            )

        except httpx.TimeoutException:
            logger.warning(f"LRCLIB timeout for {artist} - {song}")
            return None
        except Exception as e:
            logger.error(f"LRCLIB error: {e}")
            return None
