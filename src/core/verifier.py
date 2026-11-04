"""Result verification with a confidence score.

Every provider response is untrusted input. ``verify_result`` combines the
existing title/artist matcher with duration, content, and LRC sanity checks and
returns a single 0..1 confidence value.

Routing (Lyrica v2 design, section 8):

* ``>= 0.85``  accept
* ``0.60-0.85`` accept, but log as suspicious (a future revision can escalate
  to a quality provider)
* ``< 0.60``   reject
"""

from __future__ import annotations

import re
from typing import Any

from src.logger import get_logger
from src.validator import (
    extract_artist_song_from_result,
    get_similarity_ratio,
    validate_lyrics_match,
)

logger = get_logger("verifier")

ACCEPT_CONFIDENCE = 0.85
MIN_CONFIDENCE = 0.60

# Weights are starting values from the design and are easy to tune here.
_W_TITLE = 0.35
_W_ARTIST = 0.25
_W_DURATION = 0.20
_W_CONTENT = 0.10
_W_LRC = 0.10

_HTML_RE = re.compile(r"<\s*(?:html|body|head|div|!doctype)", re.IGNORECASE)
_BOILERPLATE = (
    "lyrics not available",
    "no lyrics found",
    "lyrics are not available",
    "couldn't find lyrics",
    "could not find lyrics",
    "sorry, we don't have",
    "instrumental",
    "this song is instrumental",
)
_MAX_CONTENT_BYTES = 1_000_000


def _timed_lines(result: dict) -> list:
    timed = result.get("timed_lyrics") or result.get("timedLyrics") or []
    return timed if isinstance(timed, list) else []


def _result_text(result: dict) -> str:
    lyrics = result.get("lyrics") or result.get("plain_lyrics") or result.get("lyrics_text")
    if isinstance(lyrics, str) and lyrics.strip():
        return lyrics
    parts = []
    for line in _timed_lines(result):
        if isinstance(line, dict):
            parts.append(str(line.get("text") or line.get("line") or ""))
        elif isinstance(line, str):
            parts.append(line)
    return "\n".join(parts)


def _duration_ms(result: dict) -> int | None:
    for key in ("duration_ms", "durationMs", "trackDurationMs"):
        value = result.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return int(value)
    value = result.get("duration")
    if isinstance(value, (int, float)) and value > 0:
        # LRCLIB and most sources report seconds; very large values are ms.
        return int(value) if value > 10000 else int(value * 1000)
    return None


def _content_score(result: dict) -> tuple[float, str]:
    text = _result_text(result)
    if not text or not text.strip():
        return 0.0, "empty lyrics"
    if len(text.encode("utf-8", "ignore")) > _MAX_CONTENT_BYTES:
        return 0.0, "lyrics payload too large"
    lowered = text.casefold()
    if _HTML_RE.search(text):
        return 0.0, "HTML error page"
    for marker in _BOILERPLATE:
        if marker in lowered and len(lowered) < 400:
            return 0.0, f"boilerplate content: {marker}"
    if len(text.strip()) < 10:
        return 0.2, "lyrics too short"
    return 1.0, "ok"


def _lrc_score(result: dict) -> tuple[float | None, str]:
    lines = _timed_lines(result)
    if not lines:
        return None, "no timed lyrics"

    starts: list[int] = []
    for line in lines:
        if not isinstance(line, dict):
            continue
        raw = line.get("start_time", line.get("start", line.get("time")))
        try:
            starts.append(int(float(raw)))
        except (TypeError, ValueError):
            return 0.0, "non-numeric timestamp"

    if not starts:
        return 0.0, "no usable timestamps"

    non_monotonic = sum(1 for a, b in zip(starts, starts[1:]) if b < a)
    duration = _duration_ms(result)
    out_of_range = 0
    if duration:
        limit = duration + 10_000  # tolerate trailing silence / rounding
        out_of_range = sum(1 for value in starts if value < 0 or value > limit)

    bad = non_monotonic + out_of_range
    if bad == 0:
        return 1.0, "ok"
    return max(0.0, 1.0 - (bad / max(1, len(starts)))), "timestamps out of order or range"


def _duration_score(result: dict, expected_ms: int | None) -> tuple[float | None, str]:
    if not expected_ms:
        return None, "request duration unknown"
    actual = _duration_ms(result)
    if not actual:
        return None, "result duration unknown"
    delta = abs(actual - expected_ms)
    if delta <= 3000:
        return 1.0, "ok"
    if delta <= 10_000:
        return 0.5, f"duration delta {delta}ms"
    return 0.0, f"duration mismatch {delta}ms"


def verify_result(
    requested_artist: str,
    requested_song: str,
    result: dict | None,
    *,
    expected_duration_ms: int | None = None,
    threshold: float = 0.75,
) -> dict:
    """Verify ``result`` against the request and return a confidence verdict.

    The return value is a superset of :func:`validate_lyrics_match` so existing
    callers keep working; ``valid`` means "safe to accept" here.
    """
    if not isinstance(result, dict):
        return {
            "valid": False,
            "accepted": False,
            "confidence": 0.0,
            "reason": "no result",
            "artist_match": 0.0,
            "song_match": 0.0,
            "returned_artists": [],
            "returned_song": "",
            "script_mismatch": False,
        }

    match = validate_lyrics_match(requested_artist, requested_song, result, threshold)
    content, content_reason = _content_score(result)
    lrc, lrc_reason = _lrc_score(result)
    duration, duration_reason = _duration_score(result, expected_duration_ms)

    # Script-mismatched names cannot be compared with edit distance. The
    # matcher already bypassed similarity for that case.
    title_score = 1.0 if match.get("script_mismatch") else float(match.get("song_match", 0.0))
    artist_score = 1.0 if match.get("script_mismatch") else float(match.get("artist_match", 0.0))

    weighted: list[tuple[float, float]] = [
        (_W_TITLE, title_score),
        (_W_ARTIST, artist_score),
        (_W_CONTENT, content),
    ]
    if duration is not None:
        weighted.append((_W_DURATION, duration))
    if lrc is not None:
        weighted.append((_W_LRC, lrc))

    total_weight = sum(weight for weight, _ in weighted) or 1.0
    confidence = sum(weight * score for weight, score in weighted) / total_weight
    confidence = round(max(0.0, min(1.0, confidence)), 4)

    reasons = []
    if not match.get("valid"):
        reasons.append(match.get("reason") or "metadata mismatch")
    if content < 1.0:
        reasons.append(content_reason)
    if lrc is not None and lrc < 1.0:
        reasons.append(lrc_reason)
    if duration is not None and duration < 1.0:
        reasons.append(duration_reason)

    accepted = bool(match.get("valid")) and content > 0.0 and confidence >= MIN_CONFIDENCE

    if accepted and confidence < ACCEPT_CONFIDENCE:
        logger.info(
            "Suspicious but accepted (%.2f): %r - %r via %r",
            confidence,
            requested_artist,
            requested_song,
            result.get("source"),
        )

    return {
        **match,
        "valid": accepted,
        "accepted": accepted,
        "confidence": confidence,
        "reason": " | ".join(reasons) if reasons else "ok",
        "content_score": round(content, 3),
        "lrc_score": None if lrc is None else round(lrc, 3),
        "duration_score": None if duration is None else round(duration, 3),
    }


def score_candidate(requested_artist: str, requested_song: str, candidate: dict) -> float:
    """Cheap metadata-only score used to pick the best search hit.

    No content checks run here because search results often omit lyrics.
    """
    if not isinstance(candidate, dict):
        return 0.0
    ret_artists, ret_song = extract_artist_song_from_result(candidate)
    req_artists, _ = extract_artist_song_from_result(
        {"artist": requested_artist, "title": requested_song}
    )
    title = get_similarity_ratio(requested_song, ret_song) if ret_song else 0.0
    artist = 0.0
    for req in req_artists:
        for ret in ret_artists:
            artist = max(artist, get_similarity_ratio(req, ret))
    return round(0.6 * title + 0.4 * artist, 4)


def verdict_summary(verdict: dict) -> dict[str, Any]:
    """Small, log-safe projection (never contains lyrics or secrets)."""
    return {
        "valid": verdict.get("valid", False),
        "confidence": verdict.get("confidence", 0.0),
        "reason": verdict.get("reason", ""),
        "song_match": verdict.get("song_match", 0.0),
        "artist_match": verdict.get("artist_match", 0.0),
    }
