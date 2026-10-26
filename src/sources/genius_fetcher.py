"""
src/sources/genius_fetcher.py

Fetches plain lyrics from the Genius API + page scraping.

Implementation notes
--------------------
The Genius API does NOT return lyrics text directly; it only returns
metadata including the song's web page URL.

This implementation:
  1. GET https://api.genius.com/search?q=... with Bearer token
  2. GET the song's `url` field (genius.com/<slug>-lyrics) using
     realistic browser headers, then extract lyrics from the HTML.

The HTML parser handles Genius's fragmented layout where lyrics are
split across MULTIPLE `<div data-lyrics-container="true">` elements,
each potentially containing deeply nested inner `<div>`, `<a>`, and
`<span>` tags for annotations and interactive features.

The old regex `(.*?)</div>` terminated at the FIRST inner `</div>`,
truncating each section and causing missing verses. The new parser
tracks div nesting depth to correctly extract the full container
content, then strips inner HTML to extract clean text.

Environment variable:
  GENIUS_TOKEN  — Genius client access token from genius.com/api/clients
"""

import asyncio
import re
import html as _html
import httpx
from src.config import GENIUS_TOKEN
from src.logger import get_logger
from .base_fetcher import BaseFetcher, build_result, get_http_client

logger = get_logger("genius_fetcher")

_API_BASE = "https://api.genius.com"
_TIMEOUT = httpx.Timeout(connect=5.0, read=20.0, write=5.0, pool=3.0)

# Rotate through multiple realistic User-Agent strings to reduce bot detection
_USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) "
        "Gecko/20100101 Firefox/132.0"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/18.1 Safari/605.1.15"
    ),
]

_ua_index = 0


def _next_ua() -> str:
    """Round-robin through User-Agent strings."""
    global _ua_index
    ua = _USER_AGENTS[_ua_index % len(_USER_AGENTS)]
    _ua_index += 1
    return ua


def _browser_headers() -> dict:
    """Fresh browser-like headers for each request (rotating UA)."""
    return {
        "User-Agent": _next_ua(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.google.com/",
        "DNT": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "cross-site",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Connection": "keep-alive",
    }


# ── Regex patterns ──────────────────────────────────────────────────────────

# Locate the START of each lyrics container (we then track depth to find end)
_CONTAINER_OPEN_RE = re.compile(
    r'<div[^>]*\bdata-lyrics-container="true"[^>]*>',
    re.DOTALL | re.IGNORECASE,
)

# Elements that Genius marks as excluded from text selection (UI artifacts)
_EXCLUDE_RE = re.compile(
    r'<[^>]*\bdata-exclude-from-selection="true"[^>]*>.*?</[^>]+>',
    re.DOTALL | re.IGNORECASE,
)

# General tag patterns
_BR_RE = re.compile(r'<br\s*/?>', re.IGNORECASE)
_TAG_RE = re.compile(r'<[^>]+>')

# Strip contributor note and embed footer that Genius injects
_CONTRIBUTOR_RE = re.compile(r"^\d+\s+Contributors?.*?Lyrics\n", re.DOTALL)
_EMBED_RE = re.compile(r"\d*\s*Embed\s*$", re.IGNORECASE)

# Section header tags like [Verse 1], [Chorus], etc. — preserve them
_SECTION_HEADER_RE = re.compile(r'^\[.*?\]$', re.MULTILINE)


def _remove_excluded_elements(html_text: str) -> str:
    """
    Remove any element marked with data-exclude-from-selection="true"
    by tracking opening and matching closing tags. This prevents contributor
    counters, translation dropdowns, and UI buttons from contaminating lyrics.
    """
    pattern = re.compile(
        r'<([a-zA-Z0-9]+)[^>]*\bdata-exclude-from-selection=[\"\']true[\"\'][^>]*>',
        re.IGNORECASE,
    )
    while True:
        m = pattern.search(html_text)
        if not m:
            break
        tag = m.group(1).lower()
        start = m.start()
        pos = m.end()
        depth = 1
        open_pattern = re.compile(rf'<{tag}[\s>/]', re.IGNORECASE)
        close_tag = f'</{tag}>'

        while depth > 0 and pos < len(html_text):
            next_close = html_text.lower().find(close_tag, pos)
            if next_close == -1:
                pos = len(html_text)
                break

            chunk = html_text[pos:next_close]
            m_open = open_pattern.search(chunk)
            if m_open:
                depth += 1
                pos = pos + m_open.end()
            else:
                depth -= 1
                pos = next_close + len(close_tag)

        html_text = html_text[:start] + html_text[pos:]
    return html_text


def _extract_container_contents(html_text: str) -> list[str]:
    """
    Extract the full inner HTML of each <div data-lyrics-container="true">
    by tracking nested div depth. This avoids the classic bug where a simple
    non-greedy (.*?)</div> regex terminates at the first inner </div>.

    Returns a list of raw inner-HTML strings, one per container.
    """
    contents = []
    for m in _CONTAINER_OPEN_RE.finditer(html_text):
        start = m.end()  # position right after the opening tag
        depth = 1
        pos = start

        while depth > 0 and pos < len(html_text):
            # Find next <div or </div>
            next_open = html_text.find("<div", pos)
            next_close = html_text.find("</div>", pos)

            if next_close == -1:
                # No more closing divs — malformed HTML, take everything
                break

            if next_open != -1 and next_open < next_close:
                # Check it's an actual opening div tag (not e.g. <divider>)
                tag_end = html_text.find(">", next_open)
                if tag_end != -1:
                    tag_content = html_text[next_open:tag_end + 1]
                    # Verify it's a <div ...> tag, not <divider> or similar
                    if re.match(r'<div[\s>/]', tag_content, re.IGNORECASE):
                        depth += 1
                pos = (tag_end + 1) if tag_end != -1 else (next_open + 4)
            else:
                depth -= 1
                if depth == 0:
                    contents.append(html_text[start:next_close])
                pos = next_close + 6  # len("</div>")

    return contents


def _html_to_text(inner_html: str) -> str:
    """
    Convert inner HTML of a lyrics container to clean text.
    Properly handles <br>, nested tags, annotations, and HTML entities.
    """
    # 1. Remove elements marked as excluded from selection (UI artifacts)
    text = _remove_excluded_elements(inner_html)

    # 2. Replace <br> tags with newlines
    text = _BR_RE.sub("\n", text)

    # 3. Strip all remaining HTML tags
    text = _TAG_RE.sub("", text)

    # 4. Unescape HTML entities (e.g. &amp;, &#x27;, &quot;)
    text = _html.unescape(text)

    return text.strip()


def _clean(raw: str) -> str:
    """Remove Genius contributor notes, embed footers, and normalize spaces."""
    cleaned = _CONTRIBUTOR_RE.sub("", raw)
    cleaned = _EMBED_RE.sub("", cleaned)
    # Normalize special unicode spaces (e.g. \u2005 4-per-em space, non-breaking space, zero-width space)
    cleaned = re.sub(r'[\u2000-\u200b\u202f\u205f\u3000\xa0\ufeff]', ' ', cleaned)
    cleaned = re.sub(r'[\u200c\u200d]', '', cleaned)
    # Collapse 3+ consecutive newlines to exactly 2 (section separator)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


def _parse_lyrics_page(html_text: str) -> str | None:
    """
    Extract lyrics from a Genius song page.

    Genius stores lyrics in MULTIPLE <div data-lyrics-container="true">
    elements (one per section — verse, chorus, bridge, etc.).
    Each container can have deeply nested inner <div>, <a>, <span> tags
    for annotations and interactive features.

    This parser correctly handles the nesting by tracking div depth
    rather than using a non-greedy regex that truncates at inner </div>.
    """
    containers = _extract_container_contents(html_text)
    if not containers:
        logger.debug("No data-lyrics-container elements found in page HTML")
        return None

    sections = []
    for inner_html in containers:
        text = _html_to_text(inner_html)
        if text:
            sections.append(text)

    if not sections:
        return None

    raw = "\n\n".join(sections)
    result = _clean(raw)

    # Validate: a real song should have at least a few words
    word_count = len(result.split())
    if word_count < 5:
        logger.warning(f"Genius: parsed lyrics seem too short ({word_count} words), treating as empty")
        return None

    return result


def _extract_preloaded_lyrics(html_text: str) -> str | None:
    """
    Fallback: Try to extract lyrics from Genius's preloaded JSON state
    (React SSR data embedded in <script> tags). Some pages include lyrics
    in the __NEXT_DATA__ or window.__PRELOADED_STATE__ JSON blob.
    """
    # Try __PRELOADED_STATE__
    state_match = re.search(
        r'window\.__PRELOADED_STATE__\s*=\s*JSON\.parse\(\'(.*?)\'\)',
        html_text,
        re.DOTALL,
    )
    if state_match:
        try:
            import json
            # The state is JSON-encoded inside a JS string, so we need to
            # unescape JS string escapes first
            raw_json = state_match.group(1)
            raw_json = raw_json.replace("\\'", "'").replace("\\\\", "\\")
            data = json.loads(raw_json)

            # Navigate to lyrics in the state tree
            # Structure: songPage -> lyricsData -> body -> plain
            song_page = data.get("songPage", {})
            lyrics_data = song_page.get("lyricsData", {})
            body = lyrics_data.get("body", {})
            if isinstance(body, dict) and body.get("plain"):
                return _clean(body["plain"])
        except Exception as e:
            logger.debug(f"Could not parse __PRELOADED_STATE__: {e}")

    return None


class GeniusFetcher(BaseFetcher):
    source_name = "genius"

    async def fetch(self, artist: str, song: str, timestamps: bool = False):
        logger.info(f"Genius: searching '{artist} - {song}'")

        client = get_http_client()
        hits = []

        try:
            # ── Step 1: Official API if token is configured ───────────────
            if GENIUS_TOKEN:
                headers_api = {
                    "Authorization": f"Bearer {GENIUS_TOKEN}",
                    "User-Agent": "Lyrica/1.5 (https://github.com/Wilooper/Lyrica)",
                }
                try:
                    search_resp = await client.get(
                        f"{_API_BASE}/search",
                        params={"q": f"{song} {artist}"},
                        headers=headers_api,
                        timeout=_TIMEOUT,
                    )
                    if search_resp.status_code == 200:
                        hits = search_resp.json().get("response", {}).get("hits", [])
                    else:
                        logger.warning(f"Genius API search returned {search_resp.status_code}")
                except Exception as e:
                    logger.warning(f"Genius official API search failed: {e}")

            # ── Step 2: Public search fallback if no token or 0 hits ──────
            if not hits:
                logger.info("Genius: querying public search endpoint")
                hits = await self._public_search(client, artist, song)

            song_hit = self._find_best_match(hits, artist, song)

            if not song_hit:
                logger.info(f"Genius: no results for '{artist} - {song}'")
                return None

            page_url = song_hit.get("url", "")
            song_id = song_hit.get("id")
            r_artist = song_hit.get("primary_artist", {}).get("name", artist)
            r_title = song_hit.get("title", song)

            if not page_url:
                return None

            # ── Step 2: Try scraping the lyrics page ──────────────────────
            lyrics = await self._scrape_lyrics_page(client, page_url, artist, song)

            # ── Step 3: If scraping failed, try the /songs/{id} endpoint for plain text ──
            if not lyrics and song_id:
                lyrics = await self._try_songs_endpoint(client, song_id, headers_api)

            if not lyrics:
                logger.info(f"Genius: could not extract lyrics for '{artist} - {song}'")
                return None

            logger.info(
                f"Genius: success for '{r_artist} - {r_title}' "
                f"({len(lyrics.splitlines())} lines, {len(lyrics.split())} words)"
            )
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

    async def _public_search(self, client: httpx.AsyncClient, artist: str, song: str) -> list:
        """
        Public unauthenticated search via https://genius.com/api/search/multi.
        Used as primary/fallback when GENIUS_TOKEN is not configured.
        """
        try:
            resp = await client.get(
                "https://genius.com/api/search/multi",
                params={"q": f"{song} {artist}"},
                headers=_browser_headers(),
                timeout=_TIMEOUT,
            )
            if resp.status_code != 200:
                logger.warning(f"Genius public search returned {resp.status_code}")
                return []
            sections = resp.json().get("response", {}).get("sections", [])
            for s in sections:
                if s.get("type") == "song":
                    return s.get("hits", [])
            return []
        except Exception as e:
            logger.warning(f"Genius public search failed: {e}")
            return []

    def _find_best_match(self, hits: list, artist: str, song: str) -> dict | None:
        """Find the best matching song from Genius search hits."""
        if not hits:
            return None

        artist_lower = artist.lower()
        song_lower = song.lower()

        # Pass 1: Exact artist + title match
        for h in hits:
            if h.get("type") != "song":
                continue
            result = h.get("result", {})
            hit_artist = result.get("primary_artist", {}).get("name", "").lower()
            hit_title = result.get("title", "").lower()
            if (artist_lower in hit_artist or hit_artist in artist_lower) and \
               (song_lower in hit_title or hit_title in song_lower):
                return result

        # Pass 2: Artist match only
        for h in hits:
            if h.get("type") != "song":
                continue
            result = h.get("result", {})
            hit_artist = result.get("primary_artist", {}).get("name", "").lower()
            if artist_lower in hit_artist or hit_artist in artist_lower:
                return result

        # Pass 3: Fallback — take first song hit regardless
        for h in hits:
            if h.get("type") == "song":
                return h.get("result", {})

        return None

    async def _scrape_lyrics_page(
        self, client: httpx.AsyncClient, page_url: str, artist: str, song: str
    ) -> str | None:
        """Scrape lyrics from the Genius song page HTML."""
        try:
            page_resp = await client.get(
                page_url,
                headers=_browser_headers(),
                timeout=_TIMEOUT,
            )

            if page_resp.status_code == 403:
                logger.warning(
                    f"Genius lyrics page returned 403 for '{artist} - {song}'. "
                    "Cloudflare/bot-detection block. "
                    "Consider setting up a residential proxy via PROXY_URL."
                )
                return None

            if page_resp.status_code != 200:
                logger.warning(f"Genius page returned {page_resp.status_code}")
                return None

            html_text = page_resp.text

            # Primary: parse data-lyrics-container divs with depth tracking
            lyrics = _parse_lyrics_page(html_text)
            if lyrics:
                return lyrics

            # Fallback: try preloaded JSON state
            lyrics = _extract_preloaded_lyrics(html_text)
            if lyrics:
                logger.info("Genius: extracted lyrics from preloaded state (fallback)")
                return lyrics

            logger.debug(f"Genius: no lyrics found in page HTML for '{artist} - {song}'")
            return None

        except Exception as e:
            logger.warning(f"Genius page scraping failed: {e}")
            return None

    async def _try_songs_endpoint(
        self, client: httpx.AsyncClient, song_id: int, headers_api: dict
    ) -> str | None:
        """
        Try the /songs/{id} endpoint with ?text_format=plain.
        Some songs have a `plain` field in the lyrics body returned by the API.
        This is not officially documented but works for some songs.
        """
        try:
            resp = await client.get(
                f"{_API_BASE}/songs/{song_id}",
                params={"text_format": "plain"},
                headers=headers_api,
                timeout=_TIMEOUT,
            )
            if resp.status_code != 200:
                return None

            data = resp.json().get("response", {}).get("song", {})
            # Check for embedded lyrics in description or other fields
            # The official API doesn't return lyrics, but the endpoint
            # sometimes includes a lyrics_placeholder or similar field
            description = data.get("description", {})
            if isinstance(description, dict):
                plain = description.get("plain", "")
                # Descriptions are NOT lyrics — skip
                pass

            return None

        except Exception as e:
            logger.debug(f"Genius /songs/{song_id} fallback failed: {e}")
            return None
