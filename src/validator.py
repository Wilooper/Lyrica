"""
Lyrica API — Lyrics Validator
==============================
Validates that a fetcher result actually matches what was requested.

Core principle
--------------
The validator should REJECT obviously wrong results (searching "Nasha" and
getting "Shape of You") while ACCEPTING correct results that have messy
metadata (Punjabi stored in Gurmukhi script, duplicate artist names, feat.
annotations, romanisation variants, etc.)

Architecture
------------
1. Script-mismatch bypass  — If request is Latin but result is Gurmukhi/
   Devanagari/Arabic/Korean etc., SequenceMatcher is meaningless (score=0).
   Trust the fetcher and skip similarity entirely.

2. Length-penalised similarity — Standard SequenceMatcher over-scores when
   a short query matches a longer title ("Hello" vs "Hello Goodbye" = 0.56).
   We penalise when returned string is >1.5x longer.

3. Adaptive threshold — Short names like "Nasha" (5 chars) get a lower
   threshold than long ones like "Bohemian Rhapsody".

4. Artist check — 5 methods (direct sim / substring / feat-in-title /
   reversed-collab / extension-collab). Extension-collab only fires when the
   returned title has a recognised extension suffix (feat./remix/etc.) AND
   the extension keyword itself is the reason the artist name differs — i.e.,
   the requested title is the base of the returned title, not just a substring.
"""

from difflib import SequenceMatcher
import re
import unicodedata
from src.logger import get_logger

logger = get_logger("validator")

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# Regex that matches known title extension suffixes
# Match extension keywords that follow a song title (after normalize strips punctuation/parens)
_EXTENSION_RE = re.compile(
    r'^(?:feat(?:uring|\.?)?|ft\.?|remix|live|acoustic|cover|'
    r'version|edit|radio|official|remastered?|bonus|alt\.?|instrumental|'
    r'extended|deluxe|explicit|clean)\b',
    re.IGNORECASE,
)

# Unicode ranges for non-Latin scripts
_NON_LATIN_RANGES = [
    (0x0600, 0x06FF),   # Arabic
    (0x0900, 0x097F),   # Devanagari (Hindi)
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
    (0x3000, 0x9FFF),   # CJK (Chinese/Japanese/Korean)
    (0xAC00, 0xD7AF),   # Hangul Syllables
    (0x0400, 0x04FF),   # Cyrillic
    (0x0370, 0x03FF),   # Greek
    (0x0590, 0x05FF),   # Hebrew
]

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _has_non_latin(text: str) -> bool:
    """True if >20% of chars are from a non-Latin script."""
    if not text:
        return False
    count = sum(1 for c in text if any(lo <= ord(c) <= hi for lo, hi in _NON_LATIN_RANGES))
    return count > max(1, len(text) * 0.2)


def normalize_string(text: str) -> str:
    """NFC-normalize, strip punctuation, collapse whitespace, lowercase."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"[^\w\s]", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text)
    return text.lower().strip()


def split_artists(artist_str: str) -> list:
    """
    Split multi-artist string into deduplicated normalised names.
    'Adele, Adele' → ['adele']
    'Talwiinder & Vision' → ['talwiinder', 'vision']
    """
    if not artist_str:
        return []
    s = re.sub(r'\s*(feat\.|ft\.|featuring|with|&|and)\s*', ', ', artist_str, flags=re.I)
    seen, result = set(), []
    for part in re.split(r'\s*[,;/]\s*', s):
        n = normalize_string(part)
        if n and n not in seen:
            seen.add(n)
            result.append(n)
    return result


def extract_artist_song_from_result(result: dict) -> tuple:
    """Return (list[str], str) — normalised artist names and song title."""
    artist = (result.get("artist") or result.get("artists") or
              result.get("artist_name") or result.get("trackArtist"))
    song = (result.get("song") or result.get("song_title") or
            result.get("title") or result.get("name") or result.get("trackName"))

    if isinstance(artist, list):
        seen, artists = set(), []
        for a in artist:
            n = normalize_string(str(a))
            if n and n not in seen:
                seen.add(n); artists.append(n)
    elif isinstance(artist, str):
        artists = split_artists(artist)
    else:
        artists = []

    return artists, normalize_string(str(song or ""))


def get_similarity_ratio(s1: str, s2: str) -> float:
    """
    Length-penalised similarity.
    When the returned string is >1.5× longer than requested, we penalise the
    score to prevent short queries over-matching long titles.
    e.g. 'hello' vs 'hello goodbye': raw=0.56 → penalised=0.38  (below threshold)
    e.g. 'hello' vs 'hello':          raw=1.00 → no penalty=1.00 ✓
    """
    a = normalize_string(s1)
    b = normalize_string(s2)
    if not a or not b:
        return 0.0
    sim = SequenceMatcher(None, a, b).ratio()
    if len(b) > len(a) * 1.5:
        sim *= (0.5 + 0.5 * (len(a) / len(b)))
    return sim


def _adaptive_threshold(text: str, base: float) -> float:
    """Lower threshold for short strings to avoid unfair rejections."""
    n = len(normalize_string(text))
    if n <= 4:  return max(0.40, base - 0.35)
    if n <= 6:  return max(0.50, base - 0.20)
    if n <= 10: return max(0.60, base - 0.10)
    return base


def _is_extension_suffix(returned: str, requested: str) -> bool:
    """
    True if `returned` title is `requested` title + a recognised extension.
    e.g. 'rockstar feat 21 savage' starts with 'rockstar' and then has a feat.
    This is strict: requested must be a prefix (with possible whitespace/paren).
    """
    req = normalize_string(requested)
    ret = normalize_string(returned)
    if not ret.startswith(req):
        return False
    suffix = ret[len(req):].strip()
    # Empty suffix = exact match (not an "extension")
    if not suffix:
        return False
    # Match known extension keywords
    return bool(_EXTENSION_RE.match(suffix))


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
    Returns dict:
        valid            bool
        reason           str
        artist_match     float (0–1)
        song_match       float (0–1)
        returned_artists list[str]
        returned_song    str
        script_mismatch  bool
    """
    req_artists          = split_artists(requested_artist)
    norm_req_song        = normalize_string(requested_song)
    ret_artists, ret_song = extract_artist_song_from_result(result)

    # ── Guard: no song title → trust fetcher ─────────────────────────────────
    if not ret_song:
        logger.warning(f"No title in result — trusting fetcher for '{requested_song}'")
        return _ok("No title metadata — trusting fetcher", 1.0, 1.0,
                   ret_artists, ret_song, False)

    # ── Cross-script bypass ───────────────────────────────────────────────────
    # Latin request vs Gurmukhi/Devanagari/Arabic/Korean result → sim=0, bypass
    req_non_latin = _has_non_latin(norm_req_song)
    ret_non_latin = _has_non_latin(ret_song)
    if req_non_latin != ret_non_latin:
        logger.info(f"✓ Cross-script: '{requested_artist}-{requested_song}' → '{ret_artists}-{ret_song}'")
        return _ok("Cross-script match — similarity bypassed", 1.0, 1.0,
                   ret_artists, ret_song, True)

    # ── Adaptive thresholds ───────────────────────────────────────────────────
    song_thresh   = _adaptive_threshold(requested_song,   threshold)
    artist_thresh = _adaptive_threshold(requested_artist, threshold)

    # ── Song check ────────────────────────────────────────────────────────────
    song_sim  = get_similarity_ratio(norm_req_song, ret_song)
    # If it's a recognised extension (feat./remix/etc.), the song title IS
    # correct by definition — the requested title is the base of the returned.
    # Extension flag: returned title is requested title + feat./remix/etc.
    # If True, the song IS the requested song — just with extra attribution info.
    is_extension = _is_extension_suffix(ret_song, norm_req_song)

    song_ok = song_sim >= song_thresh or is_extension

    # ── Artist check ─────────────────────────────────────────────────────────
    best_artist = 0.0
    found       = False
    method      = "None"
    raw_ret_str = " ".join(ret_artists)

    if not ret_artists:
        # No artist metadata → song similarity alone decides
        found  = True
        method = "No artist metadata — song-only"
    else:
        for req in req_artists:
            for ret in ret_artists:
                best_artist = max(best_artist, get_similarity_ratio(req, ret))

            # A: direct similarity
            if any(get_similarity_ratio(req, ret) >= artist_thresh for ret in ret_artists):
                found  = True; method = "Direct similarity"; break

            # B: requested artist is a substring of returned artist string
            if len(req) >= 3 and req in raw_ret_str:
                found  = True; method = "Substring match"; break

            # C: requested artist appears in the song title (feat. annotation)
            if len(req) >= 3 and req in ret_song:
                found  = True; method = "Featured in title"; break

            # D: returned artist is a substring of the requested artist
            #    (reversed collab: "21 Savage" in "21 Savage & Post Malone")
            norm_req_full = normalize_string(requested_artist)
            if any(len(r) >= 3 and r in norm_req_full for r in ret_artists):
                found  = True; method = "Reversed collab"; break

            # E: extension collab — returned title is requested title + feat./remix
            #    e.g. search "Rockstar" by "Post Malone", get title
            #    "Rockstar (feat. 21 Savage)" attributed to "21 Savage" only.
            #    Accept IF: the title is genuinely an extension (prefix check)
            #    AND the artist score is above a minimum plausibility threshold.
            #    We use 0.20 minimum — this passes "post malone"↔"21 savage" (0.30)
            #    but must also check that the artist fields aren't completely
            #    unrelated (different genre/scene entirely).
            #    Extra guard: reject if best_artist == 0 (totally different names)
            if is_extension and best_artist >= 0.20:
                found  = True; method = "Extension collab accepted"; break

    # ── Decision ─────────────────────────────────────────────────────────────
    if found and song_ok:
        logger.info(f"✓ {method}: '{requested_artist}'-'{requested_song}' "
                    f"[a={best_artist:.2f} s={song_sim:.2f}]")
        return _ok(f"Matched via {method}", best_artist, song_sim,
                   ret_artists, ret_song, False)

    parts = []
    if not found:
        parts.append(f"artist score={best_artist:.2f} < {artist_thresh:.2f}")
    if not song_ok:
        parts.append(f"song score={song_sim:.2f} < {song_thresh:.2f}")
    reason = " | ".join(parts)
    logger.warning(f"✗ Rejected '{requested_artist}-{requested_song}' vs "
                   f"'{raw_ret_str}-{ret_song}': {reason}")
    return {
        "valid":            False,
        "reason":           reason,
        "artist_match":     round(best_artist, 3),
        "song_match":       round(song_sim, 3),
        "returned_artists": ret_artists,
        "returned_song":    ret_song,
        "script_mismatch":  False,
    }


def _ok(reason, artist, song, ret_artists, ret_song, script):
    return {
        "valid":            True,
        "reason":           reason,
        "artist_match":     round(float(artist), 3),
        "song_match":       round(float(song), 3),
        "returned_artists": ret_artists,
        "returned_song":    ret_song,
        "script_mismatch":  script,
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
    Validate a list of fetcher attempts.
    Each attempt: { 'api': str, 'result': dict, 'success': bool }
    Returns: { 'has_valid_match': bool, 'valid_results': list, 'all_failed': bool }
    """
    valid_results = []
    for attempt in attempts:
        if not isinstance(attempt, dict) or not attempt.get("success", True):
            continue
        result = attempt.get("result")
        if not result:
            continue
        val = validate_lyrics_match(requested_artist, requested_song, result, threshold)
        if val["valid"]:
            valid_results.append({"api": attempt.get("api"), "result": result, "validation": val})
        else:
            logger.debug(f"  Rejected [{attempt.get('api')}]: {val['reason']}")

    return {
        "has_valid_match": len(valid_results) > 0,
        "valid_results":   valid_results,
        "all_failed":      len(valid_results) == 0,
    }
