"""
Lyrica API — Lyrics Validator
==============================
Validates that a fetcher result actually matches what was requested.

Key design decisions
--------------------
* Non-Latin script awareness  — Punjabi (Gurmukhi), Hindi (Devanagari), Arabic,
  Korean, Japanese, Chinese, Cyrillic all contain zero Latin characters.
  When the returned metadata is in a different script than the request, we
  CANNOT compare them with SequenceMatcher (ratio will always be ~0.0).
  In that case we trust the fetcher and skip the similarity gate.

* Transliteration tolerance   — "Talwiinder" vs "talwiinder" after normalize,
  same person. We accept results where the song title matches AND the result
  came from a source that found it via the given query.

* Short song / artist names   — "Nasha" has only 5 chars. A 0.75 threshold
  on a 5-char string means any single char difference fails. Lower bound is
  applied for short strings automatically.

* Multiple artist strings      — "Talwiinder & Vision", "Adele, Adele",
  "Dave & Tems" — we split and deduplicate before comparing.

* Graceful fallback            — if we cannot confirm a match, we accept the
  result rather than throwing a false-negative. The validator's job is to
  REJECT obviously wrong songs (searching "Nasha" and getting "Shape of You"),
  not to be a pixel-perfect identity check.
"""

from difflib import SequenceMatcher
import re
import unicodedata
from src.logger import get_logger

logger = get_logger("validator")


# ─────────────────────────────────────────────────────────────────────────────
# Script detection
# ─────────────────────────────────────────────────────────────────────────────

_NON_LATIN_RANGES = [
    (0x0600, 0x06FF),   # Arabic
    (0x0900, 0x097F),   # Devanagari (Hindi, Marathi, Sanskrit)
    (0x0A00, 0x0A7F),   # Gurmukhi (Punjabi)
    (0x0A80, 0x0AFF),   # Gujarati
    (0x0B00, 0x0B7F),   # Oriya
    (0x0B80, 0x0BFF),   # Tamil
    (0x0C00, 0x0C7F),   # Telugu
    (0x0C80, 0x0CFF),   # Kannada
    (0x0D00, 0x0D7F),   # Malayalam
    (0x0E00, 0x0E7F),   # Thai
    (0x0F00, 0x0FFF),   # Tibetan
    (0x1100, 0x11FF),   # Hangul Jamo (Korean)
    (0x3000, 0x9FFF),   # CJK unified (Chinese/Japanese/Korean)
    (0xAC00, 0xD7AF),   # Hangul Syllables (Korean)
    (0x0400, 0x04FF),   # Cyrillic
    (0x0370, 0x03FF),   # Greek
    (0x0590, 0x05FF),   # Hebrew
]


def _has_non_latin_script(text: str) -> bool:
    """True if >20% of characters in text belong to a non-Latin script."""
    if not text:
        return False
    non_latin = sum(
        1 for ch in text
        if any(lo <= ord(ch) <= hi for lo, hi in _NON_LATIN_RANGES)
    )
    return non_latin > max(1, len(text) * 0.2)


def _scripts_compatible(s1: str, s2: str) -> bool:
    """True if both strings use the same script family (both Latin or both non-Latin)."""
    return _has_non_latin_script(s1) == _has_non_latin_script(s2)


# ─────────────────────────────────────────────────────────────────────────────
# String normalisation
# ─────────────────────────────────────────────────────────────────────────────

def normalize_string(text: str) -> str:
    """
    NFC-normalise, strip punctuation, collapse whitespace, lowercase.
    Preserves non-Latin Unicode letters so Punjabi/Hindi/etc. are intact.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    # Remove everything except word chars (unicode-aware) and spaces
    text = re.sub(r"[^\w\s]", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text)
    return text.lower().strip()


def split_artists(artist_str: str) -> list:
    """
    Split a multi-artist string → list of deduplicated normalised names.
    Handles feat./ft./featuring/&/and/,/;// separators.
    "Adele, Adele"        → ["adele"]
    "Talwiinder & Vision" → ["talwiinder", "vision"]
    """
    if not artist_str:
        return []
    artist_str = re.sub(r'\s*(feat\.|ft\.|featuring|with|&|and)\s*', ', ', artist_str, flags=re.I)
    seen, result = set(), []
    for part in re.split(r'\s*[,;/]\s*', artist_str):
        norm = normalize_string(part)
        if norm and norm not in seen:
            seen.add(norm)
            result.append(norm)
    return result


def extract_artist_song_from_result(result: dict) -> tuple:
    """Return (list_of_artist_names, song_title_normalised) from a fetcher result dict."""
    artist = (
        result.get("artist") or result.get("artists") or
        result.get("artist_name") or result.get("trackArtist")
    )
    song = (
        result.get("song") or result.get("song_title") or
        result.get("title") or result.get("name") or result.get("trackName")
    )

    if isinstance(artist, list):
        seen, returned_artists = set(), []
        for a in artist:
            n = normalize_string(str(a))
            if n and n not in seen:
                seen.add(n)
                returned_artists.append(n)
    elif isinstance(artist, str):
        returned_artists = split_artists(artist)
    else:
        returned_artists = []

    return returned_artists, normalize_string(str(song or ""))


# ─────────────────────────────────────────────────────────────────────────────
# Similarity helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_similarity_ratio(str1: str, str2: str) -> float:
    s1 = normalize_string(str1)
    s2 = normalize_string(str2)
    if not s1 or not s2:
        return 0.0
    return SequenceMatcher(None, s1, s2).ratio()


def _adaptive_threshold(text: str, base: float) -> float:
    """
    Scale threshold down for short strings to avoid unfair rejections.
    "Nasha" (5 chars) → threshold drops to ~0.50
    "Hello" (5 chars) → same
    "Bohemian Rhapsody" (17 chars) → full threshold
    """
    length = len(normalize_string(text))
    if length <= 4:
        return max(0.40, base - 0.35)
    if length <= 6:
        return max(0.50, base - 0.20)
    if length <= 10:
        return max(0.60, base - 0.10)
    return base


# ─────────────────────────────────────────────────────────────────────────────
# Core validator
# ─────────────────────────────────────────────────────────────────────────────

def validate_lyrics_match(
    requested_artist: str,
    requested_song: str,
    result: dict,
    threshold: float = 0.75,
) -> dict:
    """
    Determine whether `result` is the song that was actually requested.

    Returns dict with:
        valid            bool
        reason           str
        artist_match     float  (0–1)
        song_match       float  (0–1)
        returned_artists list[str]
        returned_song    str
        script_mismatch  bool
    """
    requested_artists        = split_artists(requested_artist)
    norm_req_song            = normalize_string(requested_song)
    returned_artists, returned_song = extract_artist_song_from_result(result)

    # ── 1. No song title in result → trust the fetcher ────────────────────────
    if not returned_song:
        logger.warning(f"No song title in result — trusting fetcher for '{requested_song}'")
        return _accept("No metadata to compare — trusting fetcher", 1.0, 1.0,
                       returned_artists, returned_song, False)

    # ── 2. Cross-script detection → bypass similarity entirely ────────────────
    #
    # Example: user searches "Nasha" (Latin) but LRCLIB returns the song stored
    # in Gurmukhi script as "ਨਸ਼ਾ" with artist "ਤਲਵਿੰਦਰ". SequenceMatcher
    # will give 0.0 for "talwiinder" vs "ਤਲਵਿੰਦਰ". That is NOT a wrong result,
    # it's simply a different encoding of the same song.
    #
    song_scripts_ok   = _scripts_compatible(norm_req_song,   returned_song)
    artist_scripts_ok = True
    if requested_artists and returned_artists:
        artist_scripts_ok = any(
            _scripts_compatible(req, ret)
            for req in requested_artists
            for ret in returned_artists
        )

    if not song_scripts_ok or not artist_scripts_ok:
        logger.info(
            f"✓ Cross-script bypass: '{requested_artist} – {requested_song}' "
            f"matched '{returned_artists} – {returned_song}' (different scripts)"
        )
        return _accept("Cross-script match — similarity bypassed", 1.0, 1.0,
                       returned_artists, returned_song, True)

    # ── 3. Adaptive thresholds for short names ────────────────────────────────
    song_thresh   = _adaptive_threshold(requested_song,   threshold)
    artist_thresh = _adaptive_threshold(requested_artist, threshold)

    # ── 4. Song title check ───────────────────────────────────────────────────
    song_sim       = get_similarity_ratio(norm_req_song, returned_song)
    # Also accept if the requested song title is a substring of the returned one
    # e.g. "Nasha" ⊂ "Nasha (feat. XYZ)"
    song_contained = len(norm_req_song) >= 3 and norm_req_song in returned_song
    song_ok        = song_sim >= song_thresh or song_contained

    # ── 5. Artist check ───────────────────────────────────────────────────────
    best_artist_score = 0.0
    found_artist      = False
    match_method      = "None"
    raw_returned_str  = " ".join(returned_artists)

    # If the result has no artist info, don't penalise — check song only
    if not returned_artists:
        found_artist = True
        match_method = "No artist metadata — song-only match"
    else:
        for req in requested_artists:
            # Update best score across all pairs
            for ret in returned_artists:
                best_artist_score = max(best_artist_score, get_similarity_ratio(req, ret))

            # Check A: direct similarity
            if any(get_similarity_ratio(req, ret) >= artist_thresh for ret in returned_artists):
                found_artist = True
                match_method = "Direct similarity"
                break

            # Check B: substring in full artist string
            if len(req) >= 3 and req in raw_returned_str:
                found_artist = True
                match_method = "Substring match"
                break

            # Check C: artist name in song title (feat. annotation)
            if len(req) >= 3 and req in returned_song:
                found_artist = True
                match_method = "Featured in title"
                break

            # Check D: reversed collab — returned artist is part of requested artist string
            # e.g. request="Post Malone", returned artist="21 Savage"
            norm_req_artist_full = normalize_string(requested_artist)
            if any(len(ret) >= 3 and ret in norm_req_artist_full for ret in returned_artists):
                found_artist = True
                match_method = "Reversed collab attribution"
                break

            # Check E: if the song title is clearly correct (either high sim OR
            # the requested title is a substring of the returned title), accept the
            # result regardless of collab artist attribution.
            # e.g. 'Rockstar' ⊂ 'Rockstar (feat. 21 Savage)' → valid even if
            # returned artist is '21 Savage' and requested artist is 'Post Malone'.
            if song_contained or song_sim >= 0.80:
                found_artist = True
                match_method = "Song title confirms identity — collab accepted"
                break

    # ── 6. Decision ───────────────────────────────────────────────────────────
    if found_artist and song_ok:
        logger.info(
            f"✓ Valid ({match_method}): '{requested_artist}' – '{requested_song}' "
            f"[artist={best_artist_score:.2f} song={song_sim:.2f}]"
        )
        return _accept(f"Matched via {match_method}", best_artist_score, song_sim,
                       returned_artists, returned_song, False)

    # Build debug reason
    parts = []
    if not found_artist:
        parts.append(f"artist score={best_artist_score:.2f} < {artist_thresh:.2f}")
    if not song_ok:
        parts.append(f"song score={song_sim:.2f} < {song_thresh:.2f}")
    reason = " | ".join(parts)

    logger.warning(
        f"✗ Rejected: '{requested_artist} – {requested_song}' vs "
        f"'{raw_returned_str} – {returned_song}' [{reason}]"
    )
    return {
        "valid":            False,
        "reason":           reason,
        "artist_match":     round(best_artist_score, 3),
        "song_match":       round(song_sim, 3),
        "returned_artists": returned_artists,
        "returned_song":    returned_song,
        "script_mismatch":  False,
    }


def _accept(reason, artist_score, song_score, returned_artists, returned_song, script_mismatch):
    return {
        "valid":            True,
        "reason":           reason,
        "artist_match":     round(float(artist_score), 3),
        "song_match":       round(float(song_score), 3),
        "returned_artists": returned_artists,
        "returned_song":    returned_song,
        "script_mismatch":  script_mismatch,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Batch validator
# ─────────────────────────────────────────────────────────────────────────────

def validate_and_filter_results(
    requested_artist: str,
    requested_song: str,
    attempts: list,
    threshold: float = 0.75,
) -> dict:
    """
    Run validate_lyrics_match over a list of fetcher attempt dicts.

    Each attempt: { "api": str, "result": dict, "success": bool }

    Returns:
        {
            "has_valid_match": bool,
            "valid_results":   list[{ api, result, validation }],
            "all_failed":      bool,
        }
    """
    valid_results   = []
    invalid_results = []

    for attempt in attempts:
        if not isinstance(attempt, dict):
            continue
        if not attempt.get("success", True):
            continue
        result = attempt.get("result")
        if not result:
            continue

        val = validate_lyrics_match(requested_artist, requested_song, result, threshold)

        if val["valid"]:
            valid_results.append({
                "api":        attempt.get("api"),
                "result":     result,
                "validation": val,
            })
        else:
            invalid_results.append({"api": attempt.get("api"), "reason": val["reason"]})
            logger.debug(f"  Rejected [{attempt.get('api')}]: {val['reason']}")

    return {
        "has_valid_match": len(valid_results) > 0,
        "valid_results":   valid_results,
        "all_failed":      len(valid_results) == 0,
    }
