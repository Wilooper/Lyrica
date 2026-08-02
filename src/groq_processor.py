"""
src/groq_processor.py

Handles lyrics translation and romanization via Groq LLM.

Uses the official `groq` Python SDK to call llama-3.3-70b-versatile.
Supports:
  - Translation to target language
  - Romanization (transliteration) to target language script
  - Both simultaneously (parallel via asyncio)
  - Line-count validation to ensure AI output integrity
  - Automatic retry with next key on failure

Usage:
    from src.groq_processor import process_lyrics

    result = await process_lyrics(
        lyrics_lines=["line1", "line2"],
        target_language="en",
        translate=True,
        romanize=True,
    )
"""

from __future__ import annotations

import asyncio
from typing import Optional

from groq import AsyncGroq, AuthenticationError, RateLimitError, APIError

from src.groq_key_manager import get_key_manager, _mask_key
from src.logger import get_logger
from src.config import GROQ_MODEL

logger = get_logger("groq_processor")

# ── Constants ────────────────────────────────────────────────────────────────
_MAX_RETRIES = 2  # Max retries with different keys on failure

_TRANSLATE_SYSTEM_PROMPT = (
    "You are a professional song lyrics translator. Your task:\n"
    "1. Translate ONLY the song lyrics provided by the user.\n"
    "2. Translate into {language}.\n"
    "3. Return EXACTLY {count} lines — one translated line for each input line.\n"
    "4. Preserve the line order exactly.\n"
    "5. Do NOT add line numbers, bullet points, explanations, notes, or any extra text.\n"
    "6. Do NOT add empty lines or extra whitespace.\n"
    "7. If a line is empty or instrumental, return it as-is.\n"
    "8. Maintain the poetic/musical feel of the lyrics in your translation.\n"
    "9. Return ONLY the translated lines, nothing else."
)

_ROMANIZE_SYSTEM_PROMPT = (
    "You are a professional lyrics transliterator/romanizer. Your task:\n"
    "1. Transliterate/romanize ONLY the song lyrics provided by the user into {language} script.\n"
    "2. Return EXACTLY {count} lines — one romanized line for each input line.\n"
    "3. Preserve the original pronunciation as closely as possible.\n"
    "4. Preserve the line order exactly.\n"
    "5. Do NOT add line numbers, bullet points, explanations, notes, or any extra text.\n"
    "6. Do NOT add empty lines or extra whitespace.\n"
    "7. If a line is empty or instrumental, return it as-is.\n"
    "8. If the lyrics are already in the target script, return them unchanged.\n"
    "9. Return ONLY the romanized lines, nothing else."
)


# ── Core Functions ───────────────────────────────────────────────────────────

async def _call_groq(
    system_prompt: str,
    user_content: str,
    api_key: str,
) -> Optional[str]:
    """
    Make a single Groq API call using the official SDK.

    Returns the response text or None on failure.
    """
    try:
        client = AsyncGroq(api_key=api_key)
        response = await client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            max_tokens=8192,
        )

        if response.choices and response.choices[0].message:
            return response.choices[0].message.content
        return None

    except AuthenticationError:
        logger.error(f"Groq auth error with key {_mask_key(api_key)}")
        get_key_manager().report_failure(api_key, 401)
        return None

    except RateLimitError:
        logger.warning(f"Groq rate limit hit for key {_mask_key(api_key)}")
        get_key_manager().report_rate_limit(api_key)
        return None

    except APIError as e:
        status = getattr(e, "status_code", 500)
        logger.error(f"Groq API error ({status}): {e}")
        if status in {401, 403}:
            get_key_manager().report_failure(api_key, status)
        return None

    except Exception as e:
        logger.error(f"Unexpected Groq error: {e}")
        return None


def _validate_output(input_lines: list[str], output_text: str) -> Optional[list[str]]:
    """
    Validate that the LLM output has the same number of lines as input.

    Returns the cleaned output lines if valid, None if mismatch.
    """
    output_lines = output_text.strip().split("\n")

    # Direct match
    if len(output_lines) == len(input_lines):
        return output_lines

    # Try stripping empty trailing/leading lines
    cleaned = [line for line in output_lines if line.strip() or True]
    # Remove only truly empty leading/trailing
    while cleaned and not cleaned[0].strip():
        cleaned.pop(0)
    while cleaned and not cleaned[-1].strip():
        cleaned.pop()

    if len(cleaned) == len(input_lines):
        return cleaned

    logger.warning(
        f"Line count mismatch: input={len(input_lines)}, "
        f"output={len(output_lines)}, cleaned={len(cleaned)}"
    )
    return None


async def _call_with_retry(
    system_prompt: str,
    user_content: str,
    input_lines: list[str],
) -> Optional[list[str]]:
    """
    Call Groq with automatic key rotation and retry on failure.

    Returns validated output lines or None.
    """
    manager = get_key_manager()

    for attempt in range(_MAX_RETRIES + 1):
        api_key = manager.get_next_key()
        if api_key is None:
            logger.error("No healthy Groq API keys available")
            return None

        logger.info(
            f"Groq call attempt {attempt + 1}/{_MAX_RETRIES + 1} "
            f"with key {_mask_key(api_key)}"
        )

        raw_output = await _call_groq(system_prompt, user_content, api_key)
        if raw_output is None:
            continue

        validated = _validate_output(input_lines, raw_output)
        if validated is not None:
            return validated

        # Line count mismatch — retry with same or next key
        logger.warning(f"Retrying due to line count mismatch (attempt {attempt + 1})")

    logger.error("All Groq retry attempts exhausted")
    return None


async def translate_lyrics(
    lyrics_lines: list[str],
    target_language: str,
) -> Optional[list[str]]:
    """
    Translate lyrics lines to the target language.

    Args:
        lyrics_lines: List of lyric text lines (no timestamps)
        target_language: Target language name (e.g., "english", "hindi", "spanish")

    Returns:
        List of translated lines (same count as input) or None on failure
    """
    if not lyrics_lines:
        return []

    system_prompt = _TRANSLATE_SYSTEM_PROMPT.format(
        language=target_language,
        count=len(lyrics_lines),
    )
    user_content = "\n".join(lyrics_lines)

    return await _call_with_retry(system_prompt, user_content, lyrics_lines)


async def romanize_lyrics(
    lyrics_lines: list[str],
    target_language: str,
) -> Optional[list[str]]:
    """
    Romanize/transliterate lyrics lines to the target language script.

    Args:
        lyrics_lines: List of lyric text lines (no timestamps)
        target_language: Target language/script name (e.g., "english", "hindi")

    Returns:
        List of romanized lines (same count as input) or None on failure
    """
    if not lyrics_lines:
        return []

    system_prompt = _ROMANIZE_SYSTEM_PROMPT.format(
        language=target_language,
        count=len(lyrics_lines),
    )
    user_content = "\n".join(lyrics_lines)

    return await _call_with_retry(system_prompt, user_content, lyrics_lines)


async def process_lyrics(
    lyrics_lines: list[str],
    target_language: str,
    translate: bool = False,
    romanize: bool = False,
) -> dict:
    """
    Process lyrics for translation and/or romanization.

    Filters out empty/blank lines before calling the LLM and reconstructs them
    afterwards to prevent line-count validation mismatches.

    When both are requested, runs them in parallel via asyncio.gather.

    Args:
        lyrics_lines: List of lyric text lines (no timestamps)
        target_language: Target language name
        translate: Whether to translate
        romanize: Whether to romanize

    Returns:
        dict with keys:
          - "translated": list[str] | None (if translate requested)
          - "romanized": list[str] | None (if romanize requested)
          - "metadata": dict with processing info
    """
    result = {
        "translated": None,
        "romanized": None,
        "metadata": {
            "target_language": target_language,
            "processed_by": f"groq/{GROQ_MODEL}",
        },
    }

    if not translate and not romanize:
        return result

    # Check if keys are available before making calls
    manager = get_key_manager()
    if not manager.has_keys:
        result["metadata"]["error"] = "No Groq API keys configured"
        return result

    # Remember empty/blank lines to re-insert them later
    non_empty_indices = []
    filtered_lines = []
    for idx, line in enumerate(lyrics_lines):
        if line.strip():
            non_empty_indices.append(idx)
            filtered_lines.append(line)

    if not filtered_lines:
        # If all lines are empty, just return them as is
        if translate:
            result["translated"] = list(lyrics_lines)
        if romanize:
            result["romanized"] = list(lyrics_lines)
        return result

    tasks = {}
    if translate:
        tasks["translated"] = translate_lyrics(filtered_lines, target_language)
    if romanize:
        tasks["romanized"] = romanize_lyrics(filtered_lines, target_language)

    # Run in parallel if both requested, otherwise just the one
    if len(tasks) == 2:
        translated_result, romanized_result = await asyncio.gather(
            tasks["translated"], tasks["romanized"]
        )
        raw_translated = translated_result
        raw_romanized = romanized_result
    elif "translated" in tasks:
        raw_translated = await tasks["translated"]
        raw_romanized = None
    else:
        raw_translated = None
        raw_romanized = await tasks["romanized"]

    # Reconstruct the original structure with blank lines preserved
    def reconstruct(processed_lines: list[str] | None) -> list[str] | None:
        if processed_lines is None:
            return None
        # Start with a copy of original lines to preserve empty ones
        reconstructed = list(lyrics_lines)
        for orig_idx, new_line in zip(non_empty_indices, processed_lines):
            reconstructed[orig_idx] = new_line
        return reconstructed

    result["translated"] = reconstruct(raw_translated)
    result["romanized"] = reconstruct(raw_romanized)

    return result
