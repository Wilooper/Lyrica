"""
src/sources/genius_fetcher.py

Fetches plain lyrics from the Genius API.

Implementation notes
--------------------
The `lyricsgenius` library combines two steps internally:
  1. Search metadata via api.genius.com  (official, token-authenticated)
  2. Scrape the lyric *page* from genius.com (unofficial, scraping)

Step 2 reliably returns 403 on datacenter / VPS IPs because Genius uses
Cloudflare and bot-detection on the public website.

This implementation does both steps directly over httpx so we can control
the headers precisely:
  - Step 1: GET https://api.genius.com/search?q=... with Bearer token
  - Step 2: GET the song's `url` field (genius.com/<slug>-lyrics) using
            a realistic browser User-Agent + Accept-Language headers,
            then parse <div data-lyrics-container> with BeautifulSoup.

Falls back to lyricsgenius if BeautifulSoup is not installed.

Environment variable:
  GENIUS_TOKEN  — Genius client access token from genius.com/api/clients
"""

import asyncio
import re
import httpx
from src.config import GENIUS_TOKEN
from src.logger import get_logger
from .base_fetcher import BaseFetcher, build_result

logger = get_logger("genius_fetcher")

_API_BASE  = "https://api.genius.com"
_PAGE_BASE = "https://genius.com"
_TIMEOUT   = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=2.0)

# Browser-like headers to avoid Cloudflare/bot blocks on genius.com page scraping
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://genius.com/",
}

# Strip contributor note and embed footer that Genius injects
_CONTRIBUTOR_RE = re.compile(r"^\d+\s+Contributors?.*?Lyrics\n", re.DOTALL)
_EMBED_RE       = re.compile(r"\d*\s*Embed\s*$", re.IGNORECASE)


def _clean(raw: str) -> str:
    cleaned = _CONTRIBUTOR_RE.sub("", raw)
    cleaned = _EMBED_RE.sub("", cleaned)
    return cleaned.strip()


def _parse_lyrics_page(html: str) -> str | None:
    """
    Extract lyrics from a Genius song page using BeautifulSoup.
    Genius stores lyrics in <div data-lyrics-container="true"> elements.
    Multiple containers exist (one per section); join them with a blank line.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        # BeautifulSoup not installed — cannot parse page
        return None

    soup = BeautifulSoup(html, "html.parser")
    containers = soup.find_all("div", attrs={"data-lyrics-container": "true"})
    if not containers:
        return None

    sections = []
    for div in containers:
        # Replace <br> with newlines before extracting text
        for br in div.find_all("br"):
            br.replace_with("\n")
        sections.append(div.get_text(separator="\n"))

    raw = "\n\n".join(sections)
    return _clean(raw) or None


class GeniusFetcher(BaseFetcher):
    source_name = "genius"

    async def fetch(self, artist: str, song: str, timestamps: bool = False):
        if not GENIUS_TOKEN:
            logger.info("Genius token not configured — skipping")
            return None

        logger.info(f"Genius: searching '{artist} - {song}'")

        headers_api = {
            "Authorization": f"Bearer {GENIUS_TOKEN}",
            "User-Agent": "Lyrica/1.0 (https://github.com/Wilooper/Lyrica)",
        }

        try:
            async with httpx.AsyncClient(
                timeout=_TIMEOUT,
                follow_redirects=True,
            ) as client:

                # ── Step 1: Search via api.genius.com (official endpoint) ──────
                search_resp = await client.get(
                    f"{_API_BASE}/search",
                    params={"q": f"{song} {artist}"},
                    headers=headers_api,
                )
                if search_resp.status_code != 200:
                    logger.warning(f"Genius API search returned {search_resp.status_code}")
                    return None

                hits = search_resp.json().get("response", {}).get("hits", [])
                song_hit = None
                artist_lower = artist.lower()
                for h in hits:
                    if h.get("type") != "song":
                        continue
                    result = h.get("result", {})
                    hit_artist = result.get("primary_artist", {}).get("name", "").lower()
                    if artist_lower in hit_artist or hit_artist in artist_lower:
                        song_hit = result
                        break
                if not song_hit and hits:
                    # Fallback: take first song hit regardless of artist match
                    for h in hits:
                        if h.get("type") == "song":
                            song_hit = h.get("result", {})
                            break

                if not song_hit:
                    logger.info(f"Genius: no results for '{artist} - {song}'")
                    return None

                page_url  = song_hit.get("url", "")
                r_artist  = song_hit.get("primary_artist", {}).get("name", artist)
                r_title   = song_hit.get("title", song)

                if not page_url:
                    return None

                # ── Step 2: Fetch lyrics page with browser headers ─────────────
                page_resp = await client.get(page_url, headers=_BROWSER_HEADERS)

                if page_resp.status_code == 403:
                    logger.warning(
                        f"Genius lyrics page returned 403 for '{artist} - {song}'. "
                        "This is a Cloudflare/bot-detection block on the server IP. "
                        "Consider setting up a residential proxy via LYRICA_CONFIG."
                    )
                    return None

                if page_resp.status_code != 200:
                    logger.warning(f"Genius page returned {page_resp.status_code}")
                    return None

                lyrics = _parse_lyrics_page(page_resp.text)
                if not lyrics:
                    logger.info(f"Genius: could not parse lyrics from page for '{artist} - {song}'")
                    return None

                logger.info(f"Genius: success for '{r_artist} - {r_title}'")
                return build_result(
                    source="genius",
                    artist=r_artist,
                    title=r_title,
                    lyrics=lyrics,
                )

        except asyncio.TimeoutError:
            logger.warning(f"Genius timeout for '{artist} - {song}'")
            return None
        except httpx.TimeoutException:
            logger.warning(f"Genius HTTP timeout for '{artist} - {song}'")
            return None
        except httpx.ConnectError as e:
            logger.error(f"Genius connection error: {e}")
            return None
        except Exception as e:
            logger.error(f"Genius error: {e}")
            return None
