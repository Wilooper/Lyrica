import asyncio
import re
from datetime import datetime, timezone, timedelta
from src.config import GENIUS_TOKEN
from src.logger import get_logger
from .base_fetcher import BaseFetcher, build_result

logger = get_logger("genius_fetcher")

# Genius prepends a contributor note to every lyric response; strip it.
_CONTRIBUTOR_RE = re.compile(r"^\d+\s+Contributors?.*?Lyrics\n", re.DOTALL)
# Also strip the trailing "Embed" footer Genius adds.
_EMBED_RE = re.compile(r"\d*\s*Embed\s*$", re.IGNORECASE)


def _clean_genius_lyrics(raw: str) -> str:
    cleaned = _CONTRIBUTOR_RE.sub("", raw)
    cleaned = _EMBED_RE.sub("", cleaned)
    return cleaned.strip()


class GeniusFetcher(BaseFetcher):
    source_name = "genius"

    def __init__(self, token: str = GENIUS_TOKEN, session_ttl: int = 86400):
        self.token = token
        self._genius = None
        self._session_born: datetime | None = None
        self._session_ttl = timedelta(seconds=session_ttl)
        # Dedicated thread-pool executor so Genius's blocking I/O never
        # blocks the main asyncio event loop.
        self._executor = None  # lazy — created on first use

    # ------------------------------------------------------------------ #
    # Session management
    # ------------------------------------------------------------------ #
    def _session_expired(self) -> bool:
        if self._genius is None or self._session_born is None:
            return True
        return datetime.now(timezone.utc) - self._session_born > self._session_ttl

    def _get_genius(self):
        if not self.token:
            return None
        if self._session_expired():
            try:
                from lyricsgenius import Genius
                self._genius = Genius(
                    self.token,
                    skip_non_songs=True,
                    remove_section_headers=True,
                    verbose=False,
                    timeout=12,
                    retries=1,          # Genius SDK has its own retry; keep low
                )
                self._session_born = datetime.now(timezone.utc)
                logger.info("Genius session (re)created")
            except Exception as e:
                logger.error(f"Failed to initialise Genius client: {e}")
                return None
        return self._genius

    # ------------------------------------------------------------------ #
    # Fetch
    # ------------------------------------------------------------------ #
    async def fetch(self, artist: str, song: str, timestamps: bool = False):
        if not self.token:
            logger.info("Genius token not configured — skipping")
            return None

        genius = self._get_genius()
        if not genius:
            return None

        try:
            logger.info(f"Attempting Genius for {artist} - {song}")
            loop = asyncio.get_event_loop()

            # Run the blocking SDK call in a thread pool to avoid blocking
            # the event loop. A 15-second wall-clock timeout guards us if
            # Genius is sluggish.
            g_song = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: genius.search_song(song, artist),
                ),
                timeout=15,
            )

            if not g_song or not getattr(g_song, "lyrics", None):
                return None

            lyrics = _clean_genius_lyrics(g_song.lyrics)
            if not lyrics:
                return None

            return build_result(
                source="genius",
                artist=g_song.artist,
                title=g_song.title,
                lyrics=lyrics,
            )

        except asyncio.TimeoutError:
            logger.warning(f"Genius timeout for {artist} - {song}")
            return None
        except Exception as e:
            logger.error(f"Genius error: {e}")
            return None
