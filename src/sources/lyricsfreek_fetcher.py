import re
import httpx
from bs4 import BeautifulSoup
from src.logger import get_logger
from .base_fetcher import BaseFetcher, get_http_client, build_result

logger = get_logger("lyricsfreek_fetcher")

_CLEANUP_RE = re.compile(r"\n*Submit Corrections.*", re.IGNORECASE | re.DOTALL)


class LyricsFreekFetcher(BaseFetcher):
    source_name = "lyricsfreek"

    async def fetch(self, artist: str, song: str, timestamps: bool = False):
        client = get_http_client()
        try:
            logger.info(f"Attempting LyricsFreek for {artist} - {song}")

            # Build slug: "the weeknd" -> "the-weeknd"
            slug_artist = re.sub(r"[^\w\s-]", "", artist.lower()).strip().replace(" ", "-")
            slug_song   = re.sub(r"[^\w\s-]", "", song.lower()).strip().replace(" ", "-")
            url = f"https://www.lyricsfreek.com/{slug_artist}/{slug_song}-lyrics"

            resp = await client.get(url)
            if resp.status_code != 200:
                return None

            soup = BeautifulSoup(resp.text, "html.parser")

            # Try multiple known selectors in priority order
            lyrics_el = (
                soup.find("div", {"class": "lyrics"})
                or soup.find("div", {"id": "lyrics"})
                or soup.select_one(".lyric-content")
            )
            if not lyrics_el:
                return None

            lyrics = _CLEANUP_RE.sub("", lyrics_el.get_text(separator="\n")).strip()
            if not lyrics:
                return None

            return build_result(
                source="lyricsfreek",
                artist=artist,
                title=song,
                lyrics=lyrics,
            )

        except httpx.TimeoutException:
            logger.warning(f"LyricsFreek timeout for {artist} - {song}")
            return None
        except Exception as e:
            logger.error(f"LyricsFreek error: {e}")
            return None
