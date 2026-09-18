import re
import html as _html
import httpx
from src.logger import get_logger
from .base_fetcher import BaseFetcher, get_http_client, build_result

logger = get_logger("lyricsfreek_fetcher")

_CLEANUP_RE = re.compile(r"\n*Submit Corrections.*", re.IGNORECASE | re.DOTALL)
_LYRICS_CONTAINER_RE = re.compile(
    r'<(?:div)[^>]*(?:class="[^"]*(?:lyrics|lyric-content)[^"]*"|id="lyrics")[^>]*>(.*?)</(?:div)>',
    re.DOTALL | re.IGNORECASE
)
_TAG_RE = re.compile(r'<[^>]+>')
_BR_RE = re.compile(r'<br\s*/?>', re.IGNORECASE)


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

            match = _LYRICS_CONTAINER_RE.search(resp.text)
            if not match:
                return None

            raw_content = match.group(1)
            text_with_newlines = _BR_RE.sub("\n", raw_content)
            clean_text = _TAG_RE.sub("", text_with_newlines)
            lyrics = _html.unescape(clean_text).strip()
            lyrics = _CLEANUP_RE.sub("", lyrics).strip()

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
