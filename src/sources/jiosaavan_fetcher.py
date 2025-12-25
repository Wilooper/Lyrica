import logging
from typing import List, Dict, Any

import requests

logger = logging.getLogger("jiosaavn_fetcher")

BASE_URL = "https://saavnapi-nine.vercel.app"



def search_jiosaavn(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    try:
        url = f"{BASE_URL}/result/?query={requests.utils.quote(query)}&lyrics=false"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        songs: List[Dict[str, Any]] = []

        if isinstance(data, list):
            raw_results = data[:limit]
        elif isinstance(data, dict) and isinstance(data.get("songs"), list):
            raw_results = data["songs"][:limit]
        else:
            raw_results = []

        for song in raw_results:
            song_id = song.get("id")
            title = song.get("song") or song.get("name") or song.get("title") or ""
            primary_artists = (
                song.get("primary_artists")
                or song.get("singers")
                or song.get("music")
                or ""
            )
            artist = str(primary_artists)
            image = song.get("image")
            thumbnail = image
            try:
                duration = int(song.get("duration", 0))
            except (TypeError, ValueError):
                duration = 0

            # THIS is the song link you want
            perma_url = song.get("perma_url")

            songs.append(
                {
                    "id": song_id,
                    "title": title,
                    "artist": artist,
                    "thumbnail": thumbnail,
                    "duration": duration,
                    "type": "song",
                    "perma_url": perma_url,  # <── added
                }
            )

        logger.info(f"JioSaavn search found {len(songs)} results for '{query}'")
        return songs

    except Exception as e:
        logger.error(f"JioSaavn search failed for '{query}': {e}")
        return []



def get_jiosaavn_stream(song_link: str) -> Dict[str, Any]:
    """
    Get streaming info for a JioSaavn song using /song endpoint.

    EXPECTS:
        song_link: full JioSaavn song URL (perma_url), e.g.
            https://www.jiosaavn.com/song/khairiyat/PwAFSRNpAWw

    RETURNS:
        {
          "stream_url": "...320.mp4",
          "title": "...",
          "thumbnail": "...",
          "duration": 280,
          "artist": "Pritam, Arijit Singh"
        }
    """
    try:
        if not song_link:
            return {
                "stream_url": None,
                "title": "",
                "thumbnail": "",
                "duration": 0,
                "artist": "",
            }

        # Your working example:
        # https://saavnapi-nine.vercel.app/song/?query=https://www.jiosaavn.com/song/khairiyat/PwAFSRNpAWw&lyrics=false
        url = f"{BASE_URL}/song/?query={song_link}&lyrics=false"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        song_info = resp.json()  # returns a single dict (no "data" wrapper)

        if not isinstance(song_info, dict):
            logger.warning(f"No valid song data for link: {song_link}")
            return {
                "stream_url": None,
                "title": "",
                "thumbnail": "",
                "duration": 0,
                "artist": "",
            }

        # Direct stream URL
        stream_url = song_info.get("media_url") or song_info.get("mediaUrl")

        # Title
        title = (
            song_info.get("song")
            or song_info.get("name")
            or song_info.get("title")
            or ""
        )

        # Artists
        primary_artists = (
            song_info.get("primary_artists")
            or song_info.get("singers")
            or song_info.get("music")
            or ""
        )
        artist = str(primary_artists)

        # Cover image
        thumbnail = song_info.get("image") or ""

        # Duration
        try:
            duration = int(song_info.get("duration", 0))
        except (TypeError, ValueError):
            duration = 0

        result = {
            "stream_url": stream_url,
            "title": title,
            "thumbnail": thumbnail,
            "duration": duration,
            "artist": artist,
        }

        if stream_url:
            logger.info(f"JioSaavn stream found for {song_link}")
        else:
            logger.warning(f"No stream URL found for {song_link}")

        return result

    except Exception as e:
        logger.error(f"JioSaavn stream fetch failed for {song_link}: {e}")
        return {
            "stream_url": None,
            "title": "",
            "thumbnail": "",
            "duration": 0,
            "artist": "",
        }
