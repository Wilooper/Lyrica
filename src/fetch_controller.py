import asyncio
from datetime import datetime, timezone
from src.logger import get_logger
from src.utils import maybe_await
from src.sources import ALL_FETCHERS
from src.validator import validate_lyrics_match   # single-result validator

logger = get_logger("fetch_controller")

# ─────────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────────

FETCHER_MAP = {
    1: "Genius",
    2: "LRCLIB",
    3: "SimpMusic",
    4: "YouTube Music",
    5: "Lyrics.ovh",
    6: "ChartLyrics",
}

DEFAULT_SYNCED_SEQUENCE = [2, 3, 4]
DEFAULT_PLAIN_SEQUENCE  = [1, 2, 3, 4, 5, 6]
FAST_MODE_SEQUENCE      = [2, 3]   # LRCLIB + SimpMusic


def _registry() -> dict:
    return {
        1: ("Genius",        ALL_FETCHERS.get("genius")),
        2: ("LRCLIB",        ALL_FETCHERS.get("lrclib")),
        3: ("SimpMusic",     ALL_FETCHERS.get("simpmusic")),
        4: ("YouTube Music", ALL_FETCHERS.get("youtube")),
        5: ("Lyrics.ovh",    ALL_FETCHERS.get("lyricsovh")),
        6: ("ChartLyrics",   ALL_FETCHERS.get("chartlyrics")),
    }


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _err(msg: str) -> dict:
    return {"status": "error", "error": {"message": msg, "timestamp": _ts()}}


# ─────────────────────────────────────────────────────────────────────────────
# Single fetcher wrapper
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_with_timeout(
    api_name: str,
    fetcher,
    artist: str,
    song: str,
    timestamps: bool,
    timeout: int = 12,
) -> dict:
    """Call one fetcher, return normalised dict. Never raises."""
    try:
        result = await asyncio.wait_for(
            maybe_await(fetcher.fetch, artist, song, timestamps=timestamps),
            timeout=timeout,
        )
        if result and result.get("lyrics"):
            return {"api": api_name, "result": result, "success": True}
        return {"api": api_name, "success": False, "reason": "no_lyrics"}

    except asyncio.TimeoutError:
        logger.warning(f"[{api_name}] timed out after {timeout}s")
        return {"api": api_name, "success": False, "reason": "timeout"}
    except Exception as e:
        logger.error(f"[{api_name}] error: {e}")
        return {"api": api_name, "success": False, "reason": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Parallel fetch  —  validate-before-cancel
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_lyrics_parallel(
    artist: str,
    song: str,
    timestamps: bool,
    fetcher_ids: list,
) -> tuple:
    """
    Race all fetchers in parallel. Validate each result as it arrives.

    THE KEY FIX
    -----------
    OLD (broken):
        LRCLIB returns wrong song → success=True
            → ALL other tasks immediately CANCELLED
            → validator runs → FAIL → error returned
            → SimpMusic never got a chance

    NEW (fixed):
        LRCLIB returns wrong song → validate → FAIL
            → log warning, keep all other tasks RUNNING
        SimpMusic returns right song → validate → PASS
            → NOW cancel remaining tasks → return winner

    The cancel only happens after a result passes validation.
    A failed validation never touches pending tasks.
    """
    reg   = _registry()
    tasks = {}   # Task → api_name

    for fid in fetcher_ids:
        if fid not in reg:
            continue
        api_name, fetcher = reg[fid]
        if not fetcher:
            continue
        task = asyncio.create_task(
            fetch_with_timeout(api_name, fetcher, artist, song, timestamps)
        )
        tasks[task] = api_name

    if not tasks:
        return None, []

    all_attempts = []
    pending      = set(tasks.keys())

    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)

        for task in done:
            attempt = await task
            all_attempts.append(attempt)

            if not attempt["success"]:
                logger.debug(f"  [{attempt['api']}] skipped — {attempt.get('reason')}")
                continue

            # ── Validate BEFORE touching pending tasks ────────────────────
            val = validate_lyrics_match(artist, song, attempt["result"], threshold=0.75)

            if val["valid"]:
                # ✓ Winner — safe to cancel now
                logger.info(
                    f"✓ [{attempt['api']}] accepted "
                    f"(artist={val['artist_match']} song={val['song_match']} "
                    f"script_mismatch={val['script_mismatch']})"
                )
                for p in pending:
                    p.cancel()
                attempt["validation"] = val
                return attempt["result"], all_attempts

            else:
                # ✗ Wrong result — DO NOT cancel, let siblings keep running
                logger.warning(
                    f"✗ [{attempt['api']}] rejected: {val['reason']} "
                    f"— {len(pending)} fetcher(s) still running"
                )

    # All fetchers exhausted, nothing passed
    logger.warning(f"All fetchers exhausted — no valid result for '{artist} - {song}'")
    return None, all_attempts


# ─────────────────────────────────────────────────────────────────────────────
# Main controller
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_lyrics_controller(
    artist_name: str,
    song_title: str,
    timestamps: bool = False,
    pass_param: bool = False,
    sequence: str | None = None,
    fast_mode: bool = False,
) -> dict:
    """
    Parallel mode  (fast_mode or multi-fetcher custom sequence):
        All fetchers run simultaneously.
        Each result validated as it arrives — first valid result wins.

    Sequential mode (default):
        Fetchers run one at a time in order.
        Each result validated before moving to the next.
    """

    # ── Resolve fetcher IDs ───────────────────────────────────────────────────
    if fast_mode:
        fetcher_ids  = FAST_MODE_SEQUENCE
        use_parallel = True
        logger.info(f"Fast mode: '{artist_name} - {song_title}'")

    elif pass_param and sequence:
        try:
            fetcher_ids = [int(x.strip()) for x in sequence.split(",") if x.strip()]
        except ValueError:
            return _err("Invalid sequence format: must be comma-separated integers")

        if (
            not fetcher_ids
            or not all(1 <= x <= 6 for x in fetcher_ids)
            or len(fetcher_ids) > 6
            or len(fetcher_ids) != len(set(fetcher_ids))
        ):
            return _err("Invalid sequence: must be unique numbers between 1 and 6")

        use_parallel = len(fetcher_ids) > 1

    else:
        fetcher_ids  = DEFAULT_SYNCED_SEQUENCE if timestamps else DEFAULT_PLAIN_SEQUENCE
        use_parallel = False

    # ── Parallel path ─────────────────────────────────────────────────────────
    if use_parallel:
        result, attempts = await fetch_lyrics_parallel(
            artist_name, song_title, timestamps, fetcher_ids
        )

        if result:
            response = {"status": "success", "data": result}
            # Surface validation scores when match wasn't perfect
            for a in attempts:
                if a.get("result") is result and a.get("validation"):
                    v = a["validation"]
                    if v["artist_match"] < 1.0 or v["song_match"] < 1.0:
                        response["validation"] = {
                            k: v[k] for k in
                            ("artist_match", "song_match", "reason", "script_mismatch")
                        }
                    break
            return response

        sources_with_results = [a["api"] for a in attempts if a.get("success")]
        if sources_with_results:
            return _err(
                f"Found results from {', '.join(sources_with_results)} but none "
                f"matched '{song_title}' by '{artist_name}'"
            )
        return _err(f"No lyrics found for '{song_title}' by '{artist_name}'")

    # ── Sequential path ───────────────────────────────────────────────────────
    reg      = _registry()
    attempts = []

    for fid in fetcher_ids:
        if fid not in reg:
            continue
        api_name, fetcher = reg[fid]

        if not fetcher:
            attempts.append({"api": api_name, "status": "not_configured"})
            continue

        try:
            raw = await maybe_await(
                fetcher.fetch, artist_name, song_title, timestamps=timestamps
            )

            if not raw or not raw.get("lyrics"):
                attempts.append({"api": api_name, "status": "no_lyrics"})
                continue

            val = validate_lyrics_match(artist_name, song_title, raw, threshold=0.75)

            if val["valid"]:
                logger.info(
                    f"✓ [{api_name}] accepted "
                    f"(artist={val['artist_match']} song={val['song_match']})"
                )
                return {"status": "success", "data": raw}
            else:
                logger.warning(
                    f"✗ [{api_name}] rejected: {val['reason']} — trying next fetcher"
                )
                attempts.append({
                    "api":    api_name,
                    "status": "validation_failed",
                    "reason": val["reason"],
                })

        except Exception as e:
            logger.error(f"[{api_name}] exception: {e}")
            attempts.append({"api": api_name, "status": "error", "message": str(e)})

    return _err(f"No lyrics found for '{song_title}' by '{artist_name}'")
