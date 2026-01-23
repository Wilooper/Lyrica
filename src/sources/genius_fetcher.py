import asyncio
from datetime import datetime, timezone, timedelta
from src.config import GENIUS_TOKEN
from src.logger import get_logger
from .base_fetcher import BaseFetcher
from lyricsgenius import Genius

logger = get_logger("genius_fetcher")

class GeniusFetcher(BaseFetcher):
    def __init__(self, token: str = GENIUS_TOKEN, session_ttl: int = 86400):
        self.token = token
        self.genius = None
        self.session_created_at = None
        self.session_ttl = session_ttl  # 24 hours in seconds (86400)
    
    def _should_refresh_session(self):
        """Check if session is older than TTL"""
        if self.genius is None or self.session_created_at is None:
            return True
        elapsed = (datetime.now(timezone.utc) - self.session_created_at).total_seconds()
        return elapsed > self.session_ttl
    
    def _get_genius(self):
        """Lazy initialize Genius instance with session management"""
        if self._should_refresh_session():
            if self.token:
                self.genius = Genius(
                    self.token,
                    skip_non_songs=True,
                    remove_section_headers=True,
                    verbose=False,
                    timeout=10
                )
                self.session_created_at = datetime.now(timezone.utc)
                logger.info("Created new Genius session")
            else:
                return None
        return self.genius
    
    async def fetch(self, artist: str, song: str, timestamps: bool = False):
        """Async fetch from Genius API"""
        if not self.token:
            logger.info("Genius token not configured.")
            return None
        
        try:
            logger.info(f"Attempting Genius for {artist} - {song}")
            
            genius = self._get_genius()
            if not genius:
                return None
            
            loop = asyncio.get_event_loop()
            g_song = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: genius.search_song(song, artist)
                ),
                timeout=15
            )
            
            if g_song and getattr(g_song, "lyrics", None):
                return {
                    "source": "genius",
                    "artist": g_song.artist,
                    "title": g_song.title,
                    "lyrics": g_song.lyrics,
                    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                }
            
            return None
        
        except Exception as e:
            logger.error(f"Genius API error: {e}")
            return None