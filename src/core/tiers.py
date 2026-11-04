"""Sync tiers and view derivation.

A cached entry stores the richest tier that was fetched. Lower tiers are
derived on demand; higher tiers are never invented. This is what lets one
provider fetch serve plain, line, word, and syllable clients.
"""

from __future__ import annotations

import copy

TIER_PLAIN = "plain"
TIER_LINE = "line"
TIER_WORD = "word"
TIER_SYLLABLE = "syllable"

TIERS = (TIER_PLAIN, TIER_LINE, TIER_WORD, TIER_SYLLABLE)
_RANK = {name: index for index, name in enumerate(TIERS)}


def tier_rank(tier: str | None) -> int:
    return _RANK.get((tier or TIER_PLAIN).lower(), 0)


def normalize_tier(tier: str | None) -> str | None:
    value = (tier or "").strip().lower()
    return value if value in _RANK else None


def requested_tier(timestamps: bool = False, word_level: bool = False, syllabus: bool = False) -> str:
    """Map the v1 boolean flags to a tier."""
    if syllabus and timestamps:
        return TIER_SYLLABLE
    if word_level and timestamps:
        return TIER_WORD
    if timestamps:
        return TIER_LINE
    return TIER_PLAIN


def _payload(result: dict | None) -> dict:
    if isinstance(result, dict) and isinstance(result.get("data"), dict):
        return result["data"]
    return result or {}


def detect_tier(result: dict | None) -> str:
    """Infer the sync tier of a provider result."""
    data = _payload(result)
    timed = data.get("timed_lyrics") or data.get("timedLyrics")
    if not isinstance(timed, list) or not timed:
        return TIER_PLAIN
    for line in timed:
        if not isinstance(line, dict):
            continue
        words = line.get("words")
        if not isinstance(words, list):
            continue
        for word in words:
            if isinstance(word, dict) and word.get("syllables"):
                return TIER_SYLLABLE
        return TIER_WORD
    return TIER_LINE


def _start(value) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _text(value) -> str:
    return str(value or "")


def _timed_lines(data: dict) -> list:
    timed = data.get("timed_lyrics") or data.get("timedLyrics")
    return timed if isinstance(timed, list) else []


def _join_plain(data: dict, timed: list) -> str:
    lyrics = data.get("lyrics") or data.get("plain_lyrics") or data.get("lyrics_text")
    if isinstance(lyrics, str) and lyrics.strip():
        return lyrics
    parts = []
    for line in timed:
        if isinstance(line, dict):
            parts.append(_text(line.get("text") or line.get("line")))
        elif isinstance(line, str):
            parts.append(line)
    return "\n".join(parts)


def _strip_words(line: dict) -> dict:
    return {key: value for key, value in line.items() if key != "words"}


def _strip_syllables(line: dict) -> dict:
    out = dict(line)
    words = line.get("words")
    if isinstance(words, list):
        out["words"] = [
            {key: value for key, value in word.items() if key != "syllables"}
            for word in words
            if isinstance(word, dict)
        ]
    return out


def derive_view(result: dict | None, target_tier: str) -> dict | None:
    """Return a copy of ``result`` downgraded to ``target_tier``.

    The source object is never mutated: cached raw entries must stay pure so a
    later request at a higher tier still sees the original timings.
    """
    if not isinstance(result, dict):
        return result
    target = normalize_tier(target_tier) or TIER_PLAIN
    detected = detect_tier(result)

    if tier_rank(target) >= tier_rank(detected):
        return copy.deepcopy(result)

    out = copy.deepcopy(result)
    data = _payload(out)
    timed = _timed_lines(data)
    if not timed:
        return out

    if target == TIER_PLAIN:
        data["lyrics"] = _join_plain(data, timed)
        data["hasTimestamps"] = False
        data.pop("timed_lyrics", None)
        data.pop("timedLyrics", None)
        data.pop("sync_level", None)
    elif target == TIER_LINE:
        data["timed_lyrics"] = [
            _strip_words(line) if isinstance(line, dict) else line for line in timed
        ]
        data["hasTimestamps"] = True
        if data.get("sync_level") in (TIER_WORD, TIER_SYLLABLE):
            data["sync_level"] = TIER_LINE
    elif target == TIER_WORD:
        # Only syllable data can be downgraded to word. A line-only result was
        # handled above by returning the (lower) detected tier unchanged.
        data["timed_lyrics"] = [
            _strip_syllables(line) if isinstance(line, dict) else line for line in timed
        ]
        data["hasTimestamps"] = True
        if data.get("sync_level") == TIER_SYLLABLE:
            data["sync_level"] = TIER_WORD
    return out


def _word_start(word: dict) -> int:
    return _start(word.get("start", word.get("start_time", word.get("time", 0))))


def _syllable_start(syllable: dict) -> int:
    return _start(syllable.get("start", syllable.get("start_time", syllable.get("time", 0))))


def to_lean(
    result: dict | None,
    tier: str | None = None,
    *,
    lite: bool = False,
    fields: set[str] | None = None,
) -> dict:
    """Convert a v1 result into the compact v2 payload.

    Line entries are ``[start_ms, text]``. Word entries append
    ``[[word_start, word], ...]`` and syllable entries append one more level.
    No per-line ``id`` and no ``end_time`` are emitted; clients derive the end
    from the next line.
    """
    data = _payload(result)
    actual_tier = normalize_tier(tier) or detect_tier(result)
    timed = _timed_lines(data)

    payload: dict = {"v": 2}
    if not lite:
        payload["src"] = data.get("source") or data.get("src")
        payload["tier"] = actual_tier
        payload["artist"] = data.get("artist")
        payload["title"] = data.get("title") or data.get("song")
        duration = data.get("duration")
        if isinstance(duration, (int, float)) and duration > 0:
            payload["dur"] = int(duration * 1000) if duration < 10000 else int(duration)
    else:
        payload["tier"] = actual_tier

    if actual_tier == TIER_PLAIN or not timed:
        payload["text"] = _join_plain(data, timed)
    else:
        lines: list = []
        for line in timed:
            if not isinstance(line, dict):
                continue
            start = _start(line.get("start_time", line.get("start", 0)))
            text = _text(line.get("text") or line.get("line"))
            if actual_tier == TIER_LINE:
                lines.append([start, text])
                continue

            words_out = []
            for word in line.get("words") or []:
                if not isinstance(word, dict):
                    continue
                word_start = _word_start(word)
                word_text = _text(word.get("text") or word.get("word"))
                if actual_tier == TIER_WORD:
                    words_out.append([word_start, word_text])
                    continue
                syllables_out = [
                    [_syllable_start(syllable), _text(syllable.get("text") or syllable.get("syllable"))]
                    for syllable in word.get("syllables") or []
                    if isinstance(syllable, dict)
                ]
                words_out.append([word_start, word_text, syllables_out])
            lines.append([start, text, words_out])
        payload["lines"] = lines

    if data.get("translation_metadata"):
        payload["tr"] = data["translation_metadata"]
    if data.get("translated_lyrics"):
        payload["tr_text"] = data["translated_lyrics"]
    if data.get("romanized_lyrics"):
        payload["rom_text"] = data["romanized_lyrics"]

    if fields:
        # ``v`` and ``tier`` are part of the protocol and always survive.
        payload = {key: value for key, value in payload.items() if key in fields or key in ("v", "tier")}
    return payload
