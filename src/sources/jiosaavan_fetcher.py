import httpx
import logging
from typing import List, Dict, Any
from .base_fetcher import get_http_client

logger = logging.getLogger("jiosaavn_fetcher")

BASE_URL = "https://saavnapi-nine.vercel.app"


def _parse_song(song: dict) -> Dict[str, Any]:
    """Extract a normalised song dict from a raw JioSaavn API result."""
    try:
        duration = int(song.get("duration", 0))
    except (TypeError, ValueError):
        duration = 0

    return {
        "id":        song.get("id"),
        "title":     song.get("song") or song.get("name") or song.get("title") or "",
        "artist":    str(
            song.get("primary_artists")
            or song.get("singers")
            or song.get("music")
            or ""
        ),
        "thumbnail": song.get("image") or "",
        "duration":  duration,
        "type":      "song",
        "perma_url": song.get("perma_url"),
    }


async def search_jiosaavn(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Search JioSaavn and return a list of normalised song dicts."""
    client = get_http_client()
    try:
        url = f"{BASE_URL}/result/"
        resp = await client.get(
            url,
            params={"query": query, "lyrics": "false"},
        )
        resp.raise_for_status()
        data = resp.json()

        if isinstance(data, list):
            raw = data[:limit]
        elif isinstance(data, dict) and isinstance(data.get("songs"), list):
            raw = data["songs"][:limit]
        else:
            raw = []

        songs = [_parse_song(s) for s in raw]
        logger.info(f"JioSaavn search found {len(songs)} results for '{query}'")
        return songs

    except httpx.TimeoutException:
        logger.warning(f"JioSaavn search timeout for '{query}'")
        return []
    except Exception as e:
        logger.error(f"JioSaavn search failed for '{query}': {e}")
        return []


async def get_jiosaavn_stream(song_link: str) -> Dict[str, Any]:
    """
    Fetch stream info for a JioSaavn perma_url.

    Returns a dict with stream_url, title, artist, thumbnail, duration.
    stream_url may be None if unavailable.
    """
    _empty = {"stream_url": None, "title": "", "thumbnail": "", "duration": 0, "artist": ""}

    if not song_link:
        return _empty

    client = get_http_client()
    try:
        resp = await client.get(
            f"{BASE_URL}/song/",
            params={"query": song_link, "lyrics": "false"},
        )
        resp.raise_for_status()
        info = resp.json()

        if not isinstance(info, dict):
            logger.warning(f"Unexpected JioSaavn response type for {song_link}")
            return _empty

        try:
            duration = int(info.get("duration", 0))
        except (TypeError, ValueError):
            duration = 0

        stream_url = info.get("media_url") or info.get("mediaUrl")
        result = {
            "stream_url": stream_url,
            "title":      info.get("song") or info.get("name") or info.get("title") or "",
            "artist":     str(
                info.get("primary_artists")
                or info.get("singers")
                or info.get("music")
                or ""
            ),
            "thumbnail":  info.get("image") or "",
            "duration":   duration,
        }

        if stream_url:
            logger.info(f"JioSaavn stream found for {song_link}")
        else:
            logger.warning(f"No stream URL in JioSaavn response for {song_link}")

        return result

    except httpx.TimeoutException:
        logger.warning(f"JioSaavn stream timeout for {song_link}")
        return _empty
    except Exception as e:
        logger.error(f"JioSaavn stream failed for {song_link}: {e}")
        return _empty
