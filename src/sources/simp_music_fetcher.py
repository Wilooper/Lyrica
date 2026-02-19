import httpx
from datetime import datetime, timezone
from src.logger import get_logger
from .base_fetcher import BaseFetcher, get_http_client, build_result, parse_lrc

logger = get_logger("simpmusic_fetcher")

API_BASE = "https://api-lyrics.simpmusic.org/v1"


class SimpMusicFetcher(BaseFetcher):
    source_name = "simpmusic"

    async def _search(self, client: httpx.AsyncClient, title: str, artist: str):
        resp = await client.get(f"{API_BASE}/search", params={"q": f"{title} {artist}"})
        resp.raise_for_status()
        return resp.json()

    async def _get_lyrics(self, client: httpx.AsyncClient, video_id: str):
        resp = await client.get(f"{API_BASE}/{video_id}")
        resp.raise_for_status()
        return resp.json()

    async def fetch(self, artist: str, song: str, timestamps: bool = False):
        client = get_http_client()
        try:
            logger.info(f"Attempting SimpMusic for {artist} - {song}")

            # Step 1: search
            search_data = await self._search(client, song, artist)
            results = (
                search_data.get("data")
                if isinstance(search_data, dict)
                else search_data
            )
            if not results:
                return None

            first = results[0]
            video_id = first.get("videoId") or first.get("id")
            if not video_id:
                return None

            # Step 2: fetch lyrics
            lyric_data = await self._get_lyrics(client, video_id)
            d = lyric_data.get("data")
            if isinstance(d, list):
                d = d[0] if d else None
            if not isinstance(d, dict):
                return None

            plain   = d.get("plainLyrics") or d.get("lyrics")
            synced  = d.get("syncedLyrics") or d.get("lrc")

            # Prefer synced when timestamps requested, fall back to plain
            lyrics  = synced if (timestamps and synced) else plain
            if not lyrics:
                return None

            timed = None
            if timestamps and synced:
                timed = parse_lrc(synced)

            return build_result(
                source="simpmusic",
                artist=first.get("artistName") or artist,
                title=first.get("title") or song,
                lyrics=lyrics,
                timed_lyrics=timed,
                has_timestamps=bool(timed),
            )

        except httpx.TimeoutException:
            logger.warning(f"SimpMusic timeout for {artist} - {song}")
            return None
        except Exception as e:
            logger.error(f"SimpMusic error: {e}")
            return None
