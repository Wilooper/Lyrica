import xml.etree.ElementTree as ET
import httpx
from src.logger import get_logger
from .base_fetcher import BaseFetcher, get_http_client, build_result

logger = get_logger("chartlyrics_fetcher")

_BASE = "http://api.chartlyrics.com/apiv1.asmx/SearchLyricDirect"


class ChartLyricsFetcher(BaseFetcher):
    source_name = "chartlyrics"

    async def fetch(self, artist: str, song: str, timestamps: bool = False):
        client = get_http_client()
        try:
            logger.info(f"Attempting ChartLyrics for {artist} - {song}")

            # Use params= so httpx URL-encodes artist/song safely
            resp = await client.get(_BASE, params={"artist": artist, "song": song})
            if resp.status_code != 200 or "<Lyric>" not in resp.text:
                return None

            root = ET.fromstring(resp.content)
            lyric = root.findtext(".//Lyric")
            if not lyric or not lyric.strip():
                return None

            return build_result(
                source="chartlyrics",
                artist=root.findtext(".//LyricArtist") or artist,
                title=root.findtext(".//LyricSong") or song,
                lyrics=lyric.strip(),
            )

        except httpx.TimeoutException:
            logger.warning(f"ChartLyrics timeout for {artist} - {song}")
            return None
        except ET.ParseError as e:
            logger.error(f"ChartLyrics XML parse error: {e}")
            return None
        except Exception as e:
            logger.error(f"ChartLyrics error: {e}")
            return None
