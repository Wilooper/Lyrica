from datetime import datetime, timezone
from src.config import GENIUS_TOKEN
from src.logger import get_logger
from .base_fetcher import BaseFetcher
from lyricsgenius import Genius

logger = get_logger("genius_fetcher")

class GeniusFetcher(BaseFetcher):
    def __init__(self, token: str = GENIUS_TOKEN):
        self.token = token

    def fetch(self, artist: str, song: str, timestamps: bool=False):
        if not self.token:
            logger.info("Genius token not configured.")
            return None
        try:
            logger.info(f"Attempting Genius for {artist} - {song}")
            genius = Genius(self.token, skip_non_songs=True, remove_section_headers=True)
            g_song = genius.search_song(song, artist)
            if g_song and getattr(g_song, "lyrics", None):
                return {
                    "source": "genius",
                    "artist": g_song.artist,
                    "title": g_song.title,
                    "lyrics": g_song.lyrics,
                    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                }
        except Exception as e:
            logger.error(f"Genius API error: {e}")
        return None
