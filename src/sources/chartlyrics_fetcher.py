import requests
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
from src.logger import get_logger
from .base_fetcher import BaseFetcher

logger = get_logger("chartlyrics_fetcher")

class ChartLyricsFetcher(BaseFetcher):
    def fetch(self, artist: str, song: str, timestamps: bool=False):
        try:
            logger.info(f"Attempting ChartLyrics for {artist} - {song}")
            url = f"http://api.chartlyrics.com/apiv1.asmx/SearchLyricDirect?artist={artist}&song={song}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200 and "<Lyric>" in response.text:
                root = ET.fromstring(response.content)
                lyric = root.findtext('.//Lyric')
                if lyric and lyric.strip():
                    return {
                        "source": "chartlyrics",
                        "artist": artist,
                        "title": song,
                        "lyrics": lyric,
                        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                    }
        except Exception as e:
            logger.error(f"ChartLyrics error: {e}")
        return None
