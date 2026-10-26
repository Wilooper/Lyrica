"""
src/sources/apple_music_fetcher.py

Fetches syllable-timed lyrics from Apple Music's private AMP API.

Adapted from the LyricaAME-py project. This is a self-contained, dependency-free
native integration — no external package required. It searches the Apple Music
catalog by artist + song title, resolves the song ID, then fetches the
syllable-lyrics TTML document from the private AMP endpoint.

Apple Music provides three granularities of synced lyrics:
  1. Syllable-level — per-syllable timing (requires &syllabus=true)
  2. Word-level     — per-word timing (requires &word=true&timestamps=true)
  3. Line-level     — per-line timing (requires &timestamps=true)

Apple Music does NOT provide plain (unsynced) lyrics, so this fetcher always
returns None when timestamps=False.

Environment variables:
  APPLE_MUSIC_DEVELOPER_TOKEN (or DEVELOPER_TOKEN) — Apple Music JWT developer
                                                      token (required to use this source)
  MUSIC_USER_TOKEN                                   — Music User Token (optional;
                                                      enables storefront auto-resolution)
  APPLE_STOREFRONT                                   — default storefront code (default: us)
  APPLE_LYRICS_LANGUAGE                              — lyrics localization (default: en-gb)
  APPLE_LYRICS_SCRIPT                                — lyrics script variant (default: en-Latn)

Usage in sequence parameter:
  8, apple_music, or APPLE_MUSIC (case-insensitive)
"""

import asyncio
import json
import os
import random
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from lxml import etree

from src.config import (
    APPLE_MUSIC_USER_TOKEN,
    APPLE_STOREFRONT,
    APPLE_LYRICS_LANGUAGE,
    APPLE_LYRICS_SCRIPT,
)
from src.logger import get_logger
from src.proxy_manager import get_proxy_manager
from .base_fetcher import BaseFetcher, build_result

logger = get_logger("apple_music_fetcher")

# ── Constants ────────────────────────────────────────────────────────────────
_AMP_BASE_URL = "https://amp-api.music.apple.com/v1"
_PUBLIC_BASE_URL = "https://api.music.apple.com/v1"

_DEFAULT_TIMEOUT = 30.0
_DEFAULT_MAX_RETRIES = 3

_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

_UA = "Lyrica/1.0 (https://github.com/Wilooper/Lyrica)"


# ── Token resolution ─────────────────────────────────────────────────────────
def _resolve_developer_token() -> str | None:
    """Resolve Apple Music developer token from env (primary: explicit var)."""
    return (
        os.getenv("APPLE_MUSIC_DEVELOPER_TOKEN")
        or os.getenv("DEVELOPER_TOKEN")
    )


def _resolve_user_token() -> str | None:
    """Resolve Apple Music Music User Token from env."""
    return os.getenv("MUSIC_USER_TOKEN")


def _resolve_storefront() -> str:
    """Resolve storefront from env, defaulting to 'us'."""
    return (os.getenv("APPLE_STOREFRONT") or APPLE_STOREFRONT or "us").lower().strip()


def _resolve_lyrics_language() -> str:
    return (os.getenv("APPLE_LYRICS_LANGUAGE") or APPLE_LYRICS_LANGUAGE or "en-gb").strip().lower()


def _resolve_lyrics_script() -> str:
    return (os.getenv("APPLE_LYRICS_SCRIPT") or APPLE_LYRICS_SCRIPT or "en-Latn").strip()


# ── Apple Music API helpers ──────────────────────────────────────────────────

def _build_am_headers(developer_token: str, user_token: str | None = None) -> dict[str, str]:
    """Construct request headers for the Apple Music AMP API."""
    headers = {
        "Origin": "https://music.apple.com",
        "Accept": "application/json",
        "User-Agent": _UA,
        "Authorization": f"Bearer {developer_token}",
    }
    if user_token:
        headers["Music-User-Token"] = user_token
    return headers


def _backoff_delay(attempt: int, base: float = 1.0, cap: float = 30.0) -> float:
    """Exponential backoff with jitter (seconds)."""
    delay = min(cap, base * (2 ** attempt))
    return delay + random.uniform(0, delay * 0.25)


async def _am_request(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    params: dict | None = None,
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> dict | None:
    """Send an AMP API request with retries, backoff, and rate-limit handling.

    Returns parsed JSON dict or None on failure.
    """
    attempt = 0
    while True:
        try:
            response = await client.request("GET", url, headers=headers, params=params)
        except httpx.TimeoutException:
            if attempt >= max_retries:
                logger.error(f"Apple Music: request timeout for {url}")
                return None
            attempt += 1
            await asyncio.sleep(_backoff_delay(attempt))
            continue
        except httpx.HTTPError as exc:
            if attempt >= max_retries:
                logger.error(f"Apple Music: transport error for {url}: {exc}")
                return None
            attempt += 1
            await asyncio.sleep(_backoff_delay(attempt))
            continue

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            delay = (
                float(retry_after)
                if retry_after and retry_after.replace(".", "", 1).isdigit()
                else _backoff_delay(attempt)
            )
            if attempt >= max_retries:
                logger.warning(f"Apple Music: rate limited (429) after {attempt + 1} attempts")
                return None
            attempt += 1
            await asyncio.sleep(delay)
            continue

        if response.status_code in _RETRYABLE_STATUS_CODES:
            if attempt >= max_retries:
                logger.warning(
                    f"Apple Music: HTTP {response.status_code} for {url} "
                    f"after {attempt + 1} attempts"
                )
                return None
            attempt += 1
            await asyncio.sleep(_backoff_delay(attempt))
            continue

        if response.status_code == 404:
            logger.info(f"Apple Music: no lyrics found (404)")
            return None

        if response.status_code != 200:
            logger.warning(f"Apple Music: HTTP {response.status_code} for {url}")
            return None

        try:
            return response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            logger.error(f"Apple Music: invalid JSON response: {exc}")
            return None


async def _am_search_songs(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    storefront: str,
    term: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Search the Apple Music catalog for songs matching a query term.

    Returns a list of {"id", "name", "artistName", "albumName"} dicts.
    """
    url = f"{_PUBLIC_BASE_URL}/catalog/{storefront}/search"
    params = {"term": term, "types": "songs", "limit": limit}
    data = await _am_request(client, url, headers, params)
    if not data:
        return []

    songs = (data.get("results") or {}).get("songs") or {}
    results: list[dict[str, Any]] = []
    for song in songs.get("data") or []:
        attrs = song.get("attributes") or {}
        if not song.get("id") or not isinstance(attrs, dict):
            continue
        results.append({
            "id": str(song["id"]),
            "name": str(attrs.get("name", "")),
            "artistName": str(attrs.get("artistName", "")),
            "albumName": attrs.get("albumName"),
        })
    return results


async def _am_resolve_storefront(
    client: httpx.AsyncClient,
    headers: dict[str, str],
) -> str:
    """Resolve the storefront from /v1/me/storefront (requires user token)."""
    url = f"{_PUBLIC_BASE_URL}/me/storefront"
    data = await _am_request(client, url, headers)
    if not data:
        return _DEFAULT_STOREFRONT
    storefronts = data.get("data") or []
    if storefronts and isinstance(storefronts[0], dict):
        sf = storefronts[0].get("id")
        if sf:
            return str(sf).lower()
    return _DEFAULT_STOREFRONT


def _extract_ttml_from_response(body: dict) -> str | None:
    """Extract the TTML document string from a syllable-lyrics JSON envelope."""
    errors = body.get("errors")
    if errors:
        logger.warning(f"Apple Music: API error in response: {errors}")
        return None

    data = body.get("data")
    if not isinstance(data, list) or not data:
        return None

    first = data[0]
    if not isinstance(first, dict):
        return None

    attributes = first.get("attributes") or {}
    ttml = attributes.get("ttml")
    if ttml is None:
        ttml = _extract_ttml_from_localizations(attributes)
    if not isinstance(ttml, str) or not ttml.strip():
        return None
    return ttml


def _extract_ttml_from_localizations(attributes: dict) -> str | None:
    """Resolve TTML from attributes.ttmlLocalizations (dict or JSON string)."""
    value = attributes.get("ttmlLocalizations")
    if value is None:
        return None
    if isinstance(value, dict):
        for v in value.values():
            if isinstance(v, str) and v.strip():
                return v
        return None
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if stripped.startswith("<"):
        return value
    try:
        decoded = json.loads(stripped)
        if isinstance(decoded, dict):
            for v in decoded.values():
                if isinstance(v, str) and v.strip():
                    return v
    except json.JSONDecodeError:
        return value
    return value


# ── TTML parsing helpers (adapted from LyricaAME-py) ─────────────────────────

_WS_RE = re.compile(r"\s+")
_PUNCTUATION_CHARS: frozenset[str] = frozenset(",.!?:;)]}")
# Apple uses this namespace for itunes:songPart attribute on <div>
_ITUNES_NS = "http://music.apple.com/lyric-ttml-internal"


def _tag_local(tag: Any) -> str:
    """Return the local element name, stripping any XML namespace."""
    if isinstance(tag, str):
        return tag.rsplit("}", 1)[-1]
    return str(tag)


def _parse_timecode(value: str | None) -> float | None:
    """Parse an Apple TTML timecode into seconds.

    Accepted forms: ``ss.sss``, ``mm:ss.sss``, ``hh:mm:ss.sss``.
    A comma decimal separator (``1,5``) is treated as a dot.
    Returns None for empty or malformed values.
    """
    if not value:
        return None
    parts = value.split(":")
    if not parts:
        return None

    seconds_component = parts[-1]
    hours = 0
    minutes = 0
    if len(parts) == 3:
        try:
            hours = int(parts[0])
            minutes = int(parts[1])
        except ValueError:
            return None
    elif len(parts) == 2:
        try:
            minutes = int(parts[0])
        except ValueError:
            return None

    try:
        seconds = float(seconds_component.replace(",", "."))
    except ValueError:
        return None
    return float(hours * 3600 + minutes * 60) + seconds


def _collapse_whitespace(text: str) -> str:
    """Collapse runs of whitespace to a single space and trim."""
    if not text:
        return ""
    return _WS_RE.sub(" ", text).strip()


def _is_non_ascii_latin(ch: str) -> bool:
    """True for a single non-ASCII Latin character (e.g. é, ù, à)."""
    if not ch or len(ch) != 1 or ch.isascii():
        return False
    try:
        return unicodedata.name(ch, "").startswith("LATIN ")
    except ValueError:
        return False


def _merge_accented_tokens(text: str) -> str:
    """Merge 'o ù' style token pairs into 'où'."""
    parts = text.split(" ")
    if len(parts) <= 1:
        return text
    out: list[str] = []
    index = 0
    while index < len(parts):
        current = parts[index]
        if (
            len(current) == 1
            and current.isascii()
            and current.isalpha()
            and index + 1 < len(parts)
        ):
            nxt = parts[index + 1]
            if len(nxt) == 1 and _is_non_ascii_latin(nxt):
                out.append(current + nxt)
                index += 2
                continue
        out.append(current)
        index += 1
    return " ".join(out)


def _should_avoid_preceding_space(
    token: str, previous_token: str | None
) -> bool:
    """True when a space must not be inserted before *token*.

    Rules (from MusanovaKit):
      - ASCII punctuation starts a token: no space before it.
      - A single ASCII letter followed by a single non-ASCII Latin letter
        (e.g. ``o`` + ``ù``) is a continuation of the same word.
    """
    if not token:
        return False
    if token[0] in _PUNCTUATION_CHARS:
        return True
    if (
        previous_token
        and len(previous_token) == 1
        and previous_token.isascii()
        and previous_token.isalpha()
    ):
        if " " in token:
            first_word = token.split(" ")[0]
            if len(first_word) == 1 and _is_non_ascii_latin(first_word):
                return True
        elif len(token) == 1 and _is_non_ascii_latin(token):
            return True
    return False


def _assemble_text(tokens: list[tuple[str, bool]]) -> str:
    """Rebuild line text from tokens with leading-space flags.

    ``tokens`` is a document-ordered list of ``(text, needs_leading_space)``.
    """
    result = ""
    previous_token: str | None = None
    for text, needs_space in tokens:
        if not text:
            continue
        if not result:
            result = text
            previous_token = text
            continue
        avoid_space = _should_avoid_preceding_space(text, previous_token)
        if needs_space and not avoid_space and not result.endswith(" "):
            result += " "
        result += text
        previous_token = text
    return result


# ── Internal dataclasses for TTML parsing ────────────────────────────────────

class _SpanItem:
    """Internal representation of one timed ``<span>`` during a line walk."""

    __slots__ = ("text", "start_time", "end_time", "leading_space", "timed")

    def __init__(self, text: str, start_time: float, end_time: float,
                 leading_space: bool = False, timed: bool = True):
        self.text = text
        self.start_time = start_time
        self.end_time = end_time
        self.leading_space = leading_space
        self.timed = timed


class _PlainItem:
    """Plain (untimed) character data directly inside a ``<p>``."""

    __slots__ = ("text", "leading_space")

    def __init__(self, text: str, leading_space: bool = False):
        self.text = text
        self.leading_space = leading_space


_LineItem = _SpanItem | _PlainItem


# ── TTML → Lyrica timed_lyrics conversion ────────────────────────────────────

class _TTMLConverter:
    """Convert an Apple TTML document into Lyrica's timed_lyrics format.

    Bridges Apple's syllable-level TTML to Lyrica's line-level (and optional
    word-level / syllable-level) timed_lyrics schema.
    """

    def convert(
        self,
        ttml_text: str,
        word_level: bool = False,
        syllabus: bool = False,
    ) -> tuple[str, list[dict], str]:
        """Parse Apple TTML and return (plain_text, timed_lyrics, sync_level).

        Args:
            ttml_text:   Raw Apple TTML string.
            word_level:  If True, include per-word timing in each line entry.
            syllabus:    If True, include per-syllable timing within each word.

        Returns:
            (plain_text, timed_lyrics_list, sync_level)
            sync_level is one of "line", "word", or "syllable".
        """
        if not ttml_text or not ttml_text.strip():
            return "", [], "line"

        try:
            root = etree.fromstring(ttml_text.encode("utf-8"))
        except (etree.XMLSyntaxError, ValueError) as exc:
            logger.warning(f"Apple Music: invalid TTML: {exc}")
            return "", [], "line"

        paragraphs = self._parse_paragraphs(root)
        if not paragraphs:
            return "", [], "line"

        plain_lines: list[str] = []
        timed_lines: list[dict] = []
        idx = 0
        sync_level = "line"

        for para in paragraphs:
            for line in para:
                text = line["text"]
                if not text:
                    continue
                plain_lines.append(text)

                start_ms = _sec_to_ms(line["start"])
                end_ms = _sec_to_ms(line["end"])

                # Fill missing timings
                if start_ms is None:
                    start_ms = 0
                if end_ms is None:
                    # Use next line's start or line start + 4000ms
                    end_ms = start_ms + 4000

                entry: dict = {
                    "id": f"am_{idx}",
                    "text": text,
                    "start_time": start_ms,
                    "end_time": end_ms,
                }

                if word_level or syllabus:
                    words = self._build_words(line.get("spans", []))
                    if words:
                        word_entries = []
                        for w in words:
                            w_start = _sec_to_ms(w["start"])
                            w_end = _sec_to_ms(w["end"])
                            if w_start is None:
                                w_start = start_ms
                            if w_end is None:
                                w_end = w_start + 2000

                            wd: dict[str, Any] = {
                                "text": w["text"],
                                "start": w_start,
                                "end": w_end,
                            }

                            if syllabus and w.get("syllables"):
                                wd["syllables"] = [
                                    {
                                        "text": s["text"],
                                        "start": _sec_to_ms(s["start"]),
                                        "end": _sec_to_ms(s["end"]),
                                    }
                                    for s in w["syllables"]
                                    if s["text"]
                                ]
                                sync_level = "syllable"
                            elif word_level:
                                sync_level = "word"

                            word_entries.append(wd)

                        if word_entries:
                            entry["words"] = word_entries

                timed_lines.append(entry)
                idx += 1

        plain_text = "\n".join(plain_lines)

        # Determine final sync_level — prefer the most granular available
        if syllabus and not any("words" in e for e in timed_lines):
            # Syllable requested but no timing data available
            sync_level = "line" if timed_lines else "none"
        elif word_level and not any("words" in e for e in timed_lines):
            sync_level = "line" if timed_lines else "none"
        else:
            # sync_level is already set to "syllable" or "word" above
            if not timed_lines:
                sync_level = "none"
            elif not any("words" in e for e in timed_lines):
                sync_level = "line"

        return plain_text, timed_lines, sync_level

    # ── Parsing structure ────────────────────────────────────────────

    def _parse_paragraphs(self, root: Any) -> list[list[dict]]:
        """Walk the TTML tree, extracting lines (list of line dicts) per <div>."""
        paragraphs: list[list[dict]] = []
        for element in root.iter():
            if _tag_local(element.tag) != "div":
                continue
            lines = self._parse_div(element)
            if lines:
                paragraphs.append(lines)
        return paragraphs

    def _parse_div(self, div: Any) -> list[dict]:
        """Extract lines from a <div> element."""
        lines: list[dict] = []
        for element in div.iter():
            if _tag_local(element.tag) != "p":
                continue
            line = self._parse_p(element)
            if line:
                lines.append(line)
        return lines

    def _parse_p(self, p: Any) -> dict | None:
        """Parse a <p> element into a line dict with text, timing, and spans."""
        items = self._scan_p(p)

        line_begin = _parse_timecode(p.get("begin"))
        line_end = _parse_timecode(p.get("end"))

        spans = [i for i in items if isinstance(i, _SpanItem) and i.text]

        # Assemble canonical line text
        tokens: list[tuple[str, bool]] = []
        for item in items:
            text = _merge_accented_tokens(_collapse_whitespace(item.text))
            if text:
                tokens.append((text, item.leading_space))
        line_text = _assemble_text(tokens)

        if not line_text and not spans:
            return None

        # If no span timing but p has begin/end, create a synthetic span
        if not spans and line_text and line_begin is not None:
            spans = [_SpanItem(
                text=line_text,
                start_time=line_begin,
                end_time=line_end if line_end is not None else line_begin,
                leading_space=False,
                timed=True,
            )]

        return {
            "text": line_text,
            "start": line_begin,
            "end": line_end,
            "spans": [
                {"text": s.text, "start": s.start_time, "end": s.end_time}
                for s in spans
            ],
        }

    def _scan_p(self, p: Any) -> list[_LineItem]:
        """Walk a <p> element in document order, flattening nested spans.

        Produces one _SpanItem per leaf span with text, and one _PlainItem
        per chunk of character data outside any span.
        """
        items: list[_LineItem] = []

        def _walk(el: Any, span_begin: float | None, span_end: float | None,
                  pending_space: bool) -> bool:
            """Return the pending-whitespace state after processing *el*."""
            local = _tag_local(el.tag)
            if local == "span":
                if el.get("begin") is not None:
                    span_begin = _parse_timecode(el.get("begin"))
                if el.get("end") is not None:
                    span_end = _parse_timecode(el.get("end"))

            if el.text:
                pending_space = self._consume_chunk(
                    items, local, el.text, span_begin, span_end, pending_space
                )

            for child in el:
                pending_space = _walk(
                    child,
                    span_begin if local == "span" else None,
                    span_end if local == "span" else None,
                    pending_space,
                )
                if child.tail:
                    pending_space = self._consume_chunk(
                        items, local, child.tail, span_begin, span_end, pending_space
                    )

            return pending_space

        _walk(p, None, None, False)
        return items

    def _consume_chunk(
        self,
        items: list[_LineItem],
        local: str,
        text: str,
        span_begin: float | None,
        span_end: float | None,
        pending_space: bool,
    ) -> bool:
        """Append the item(s) for one character-data chunk."""
        if not text:
            return pending_space
        if text.isspace():
            return True
        if text[0].isspace():
            pending_space = True
        item = self._make_item(local, text, span_begin, span_end, pending_space)
        if item.text:
            items.append(item)
        return text[-1].isspace()

    def _make_item(
        self,
        local: str,
        text: str,
        span_begin: float | None,
        span_end: float | None,
        leading_space: bool,
    ) -> _LineItem:
        text = _collapse_whitespace(text)
        if not text:
            return _PlainItem("", leading_space)
        if local == "span":
            timed = span_begin is not None or span_end is not None
            start = span_begin if span_begin is not None else 0.0
            end = span_end if span_end is not None else start
            return _SpanItem(text, start, end, leading_space, timed)
        return _PlainItem(text, leading_space)

    def _build_words(self, spans: list[dict]) -> list[dict]:
        """Group consecutive spans into words, with syllable breakdown.

        Algorithm: iterate spans in document order. A new word starts when
        the current span is preceded by literal whitespace and no merge rule
        applies (punctuation / ASCII+non-ASCII adjacency).
        """
        words: list[dict] = []
        current: list[dict] = []
        previous_token: str | None = None

        for span in spans:
            boundary = False
            if current:
                boundary = span["leading_space"] and not _should_avoid_preceding_space(
                    span["text"], previous_token
                )
            if not current or boundary:
                if current:
                    words.append(self._make_word(current))
                current = [span]
            else:
                current.append(span)
            previous_token = span["text"]

        if current:
            words.append(self._make_word(current))
        return words

    def _make_word(self, spans: list[dict]) -> dict:
        """Build a word dict from grouped syllable spans."""
        syllables = [
            {
                "text": _merge_accented_tokens(s["text"]),
                "start": s["start"],
                "end": s["end"],
            }
            for s in spans
            if _merge_accented_tokens(s["text"])
        ]
        if not syllables:
            return {"text": "", "start": None, "end": None, "syllables": []}

        text = "".join(s["text"] for s in syllables)
        timed_syllables = [s for s in syllables if s["start"] is not None]
        start = timed_syllables[0]["start"] if timed_syllables else None
        end = timed_syllables[-1]["end"] if timed_syllables else None

        return {
            "text": text,
            "start": start,
            "end": end,
            "syllables": syllables,
        }


def _sec_to_ms(seconds: float | None) -> int | None:
    """Convert seconds (float) to milliseconds (int). None passthrough."""
    if seconds is None:
        return None
    return int(round(seconds * 1000))


# ── Syllable-level timing check ──────────────────────────────────────────────

def _has_syllable_timing(ttml_text: str) -> bool:
    """Quick check: does the TTML contain any timed <span> elements?"""
    if not ttml_text:
        return False
    return "<span" in ttml_text and "begin" in ttml_text


# ── Fetcher ──────────────────────────────────────────────────────────────────

class AppleMusicFetcher(BaseFetcher):
    source_name = "apple_music"

    def __init__(self):
        self._developer_token = _resolve_developer_token()
        self._user_token = _resolve_user_token()
        self._storefront = _resolve_storefront()
        self._lyrics_language = _resolve_lyrics_language()
        self._lyrics_script = _resolve_lyrics_script()

        if self._developer_token:
            logger.info(
                f"Apple Music: developer token configured "
                f"(storefront={self._storefront})"
            )
        else:
            logger.warning(
                "Apple Music: APPLE_MUSIC_DEVELOPER_TOKEN (or DEVELOPER_TOKEN) "
                "not set — this source will be skipped. "
                "Set the env var to enable Apple Music lyrics."
            )

    async def fetch(
        self,
        artist: str,
        song: str,
        timestamps: bool = False,
        word_level: bool = False,
        syllabus: bool = False,
    ):
        """Fetch lyrics from Apple Music.

        Args:
            artist:      Artist name.
            song:        Song title.
            timestamps:  Must be True — Apple Music does not provide plain
                        lyrics. Returns None when False.
            word_level:  If True (and timestamps=True), include per-word timing.
            syllabus:    If True (and timestamps=True), include per-syllable
                        timing. Apple Music is the only source that supports this.

        Returns:
            build_result dict or None.
        """
        # Apple Music only provides synced (TTML) lyrics — no plain text.
        if not timestamps:
            logger.debug("Apple Music: skipped (timestamps=false — no plain lyrics)")
            return None

        if not self._developer_token:
            logger.debug("Apple Music: skipped (no developer token)")
            return None

        # Resolve storefront: from env, or auto-resolve via user token
        storefront = self._storefront
        headers = _build_am_headers(self._developer_token, self._user_token)

        proxy = get_proxy_manager().get_next()
        transport = httpx.AsyncHTTPTransport(retries=3)
        client_kwargs: dict[str, Any] = {
            "transport": transport,
            "timeout": httpx.Timeout(connect=5.0, read=20.0, write=5.0, pool=2.0),
            "headers": {"User-Agent": _UA},
            "follow_redirects": True,
        }
        if proxy:
            client_kwargs["proxy"] = proxy

        try:
            async with httpx.AsyncClient(**client_kwargs) as client:
                # ── Auto-resolve storefront if not explicitly set ────────────
                if not os.getenv("APPLE_STOREFRONT") and not self._storefront:
                    storefront = await _am_resolve_storefront(client, headers)

                # ── Step 1: Search catalog for the song ──────────────────────
                term = f"{song} {artist}"
                logger.info(
                    f"Apple Music: searching '{term}' "
                    f"(storefront={storefront})"
                )

                songs = await _am_search_songs(client, headers, storefront, term, limit=5)
                if not songs:
                    logger.info(f"Apple Music: no results for '{term}'")
                    return None

                # ── Step 2: Try each search result for lyrics ────────────────
                # Prefer exact artist match
                artist_lower = artist.lower()
                ranked = []
                for s in songs:
                    s_artist = s.get("artistName", "").lower()
                    if artist_lower in s_artist:
                        ranked.insert(0, s)
                    else:
                        ranked.append(s)

                ttml_text = None
                matched_song = None
                for song_info in ranked[:3]:
                    song_id = song_info.get("id")
                    if not song_id:
                        continue

                    # Build per-request headers (storefront may change)
                    req_headers = _build_am_headers(
                        self._developer_token, self._user_token
                    )

                    url = (
                        f"{_AMP_BASE_URL}/catalog/{storefront}/songs/{song_id}"
                        "/syllable-lyrics"
                    )
                    params = {
                        "l[lyrics]": self._lyrics_language,
                        "l[script]": self._lyrics_script,
                        "extend": "ttmlLocalizations",
                    }

                    data = await _am_request(client, url, req_headers, params)
                    if not data:
                        continue

                    ttml_text = _extract_ttml_from_response(data)
                    if ttml_text:
                        matched_song = song_info
                        break

                if not ttml_text:
                    logger.info(
                        f"Apple Music: no syllable lyrics found for '{artist} - {song}'"
                    )
                    return None

                # ── Step 3: Parse TTML into Lyrica format ────────────────────
                converter = _TTMLConverter()
                plain_text, timed_lyrics, sync_level = converter.convert(
                    ttml_text,
                    word_level=word_level,
                    syllabus=syllabus,
                )

                if not plain_text:
                    logger.info(f"Apple Music: parsed lyrics are empty for '{artist} - {song}'")
                    return None

                # If syllable requested but not available, downgrade
                if syllabus and sync_level != "syllable":
                    logger.info(
                        f"Apple Music: syllable-level not available "
                        f"(sync_level={sync_level}), returning best available"
                    )

                # If word-level requested but not available, downgrade
                if word_level and sync_level == "line":
                    logger.info(
                        f"Apple Music: word-level not available, "
                        f"returning line-level"
                    )

                result = build_result(
                    source="apple_music",
                    artist=matched_song.get("artistName", artist) if matched_song else artist,
                    title=matched_song.get("name", song) if matched_song else song,
                    lyrics=plain_text,
                    timed_lyrics=timed_lyrics if timestamps else None,
                    has_timestamps=bool(timed_lyrics),
                    album=matched_song.get("albumName") if matched_song else None,
                    song_id=matched_song.get("id") if matched_song else None,
                    storefront=storefront,
                    sync_level=sync_level,
                )

                logger.info(
                    f"Apple Music: success for '{artist} - {song}' "
                    f"(sync_level={sync_level}, "
                    f"lines={len(timed_lyrics)})"
                )
                return result

        except asyncio.TimeoutError:
            logger.warning(f"Apple Music timeout for '{artist} - {song}'")
            return None
        except httpx.TimeoutException:
            logger.warning(f"Apple Music HTTP timeout for '{artist} - {song}'")
            return None
        except httpx.ConnectError as e:
            logger.error(f"Apple Music connection error: {e}")
            if proxy:
                get_proxy_manager().mark_failure(proxy)
            return None
        except Exception as e:
            logger.error(f"Apple Music error: {e}")
            if proxy:
                get_proxy_manager().mark_failure(proxy)
            return None
