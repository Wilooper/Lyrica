"""Canonical request normalization.

Lyrics are immutable, so one song should be fetched once and reused for every
flag combination. To make that possible the cache key must be built from a
stable identity instead of the raw query string.

Normalization rules (from the Lyrica v2 design):

* Unicode NFKC + case folding.
* Drop ``feat.`` / ``ft.`` collaborators and their trailing text.
* Drop noisy edition suffixes such as ``(Remastered)``, ``(Live)``, ``(Radio
  Edit)``, ``(Deluxe Edition)``.
* Strip punctuation, collapse whitespace.
"""

from __future__ import annotations

import re
import unicodedata

# Bracketed edition/attribution segments are removed only when they actually
# contain a noise keyword. This keeps legitimate titles like "Live Forever".
_BRACKET_RE = re.compile(r"[\(\[\{][^\)\]\}]*[\)\]\}]")
_BRACKET_KEYWORDS_RE = re.compile(
    r"\b(?:feat|ft|remaster(?:ed|ing)?|live|version|edit|deluxe|bonus|explicit|clean|acoustic|instrumental"
    r"|official|video|audio|lyrics?|visuali[sz]er)\b",
    re.IGNORECASE,
)
# "Song feat. X" / "Song ft. X" tails.
_FEAT_TAIL_RE = re.compile(r"\b(?:feat(?:uring)?|ft)\.?\s+.*$", re.IGNORECASE)
# "Song - Remastered", "Song - Live at Wembley", "Song - Radio Edit", ...
_EDITION_TAIL_RE = re.compile(
    r"""
    \s*[-–—]\s*
    (?:
        (?:(?:19|20)\d{2}\s+)?(?:re)?master(?:ed|ing)?(?:\s+(?:version|(?:19|20)\d{2}))?
      | live(?:\s+(?:version|at|from|in)\b.*)?
      | radio\s+edit
      | deluxe(?:\s+edition)?
      | bonus\s+track
      | clean\s+version
      | (?:official\s+)?(?:music\s+)?(?:video|audio|lyric\s+video)
      | lyric\s+video
      | visuali[sz]er
    )
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

_APOSTROPHE_RE = re.compile(r"[\u2018\u2019\u02bc`´]")
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+", re.UNICODE)
_AND_RE = re.compile(r"\s*&\s*")

# A sequence equal to the default order carries no extra information.
DEFAULT_SEQUENCE = "1,2,3,4,5,6,7,8"


def _strip_bracket_noise(text: str) -> str:
    def _replace(match: re.Match) -> str:
        return " " if _BRACKET_KEYWORDS_RE.search(match.group(0)) else match.group(0)

    return _BRACKET_RE.sub(_replace, text)


def normalize_text(value: str | None) -> str:
    """Return the canonical form of an artist/title string."""
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    text = _APOSTROPHE_RE.sub("", text)
    text = _AND_RE.sub(" and ", text)
    text = _strip_bracket_noise(text)
    text = _FEAT_TAIL_RE.sub(" ", text)
    text = _EDITION_TAIL_RE.sub(" ", text)
    text = _PUNCT_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text)
    return text.strip()


def normalize_identity(artist: str | None, song: str | None) -> tuple[str, str]:
    """Return ``(artist, title)`` in canonical form."""
    return normalize_text(artist), normalize_text(song)


def normalize_sequence(sequence) -> str:
    """Collapse every accepted sequence representation to one stable string.

    ``None``, the configured default order, and the literal default list all
    map to the empty string so they share a cache entry.
    """
    if sequence is None:
        return ""
    if isinstance(sequence, (list, tuple)):
        parts = [str(part).strip() for part in sequence if str(part).strip()]
    else:
        parts = [part.strip() for part in str(sequence).split(",") if part.strip()]
    value = ",".join(parts)
    return "" if value == DEFAULT_SEQUENCE else value


def duration_bucket(duration_ms: int | float | None) -> str:
    """Bucket a duration so tiny metadata differences still share a key.

    Lyrics are effectively immutable per recording; a 5-second bucket is wide
    enough to absorb source-specific rounding without merging different songs.
    """
    if not duration_ms:
        return ""
    try:
        seconds = float(duration_ms)
    except (TypeError, ValueError):
        return ""
    if seconds > 10000:  # already milliseconds
        seconds = seconds / 1000.0
    if seconds <= 0:
        return ""
    return str(int(seconds // 5))
