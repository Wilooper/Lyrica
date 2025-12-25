import requests
from datetime import datetime, timezone
from src.logger import get_logger
from .base_fetcher import BaseFetcher

logger = get_logger("lyricsovh_fetcher")

class LyricsOvhFetcher(BaseFetcher):
    def fetch(self, artist: str, song: str, timestamps: bool=False):
        try:
            logger.info(f"Attempting Lyrics.ovh API for {artist} - {song}")
            url = f"https://api.lyrics.ovh/v1/{artist}/{song}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if "lyrics" in data and data["lyrics"].strip():
                    return {
                        "source": "lyrics.ovh",
                        "artist": artist,
                        "title": song,
                        "lyrics": data["lyrics"],
                        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                    }
        except Exception as e:
            logger.error(f"Lyrics.ovh error: {e}")
        return None
