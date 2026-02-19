import asyncio
from datetime import datetime, timezone
from src.logger import get_logger
from src.utils import maybe_await
from src.sources import ALL_FETCHERS
from src.validator import validate_and_filter_results
import logging
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

logger = get_logger("fetch_controller")

# Map numeric indices to fetcher order - user-facing mapping preserved
FETCHER_MAP = {
    1: "Genius",
    2: "LRCLIB", 
    3: "SimpMusic",
    4: "YouTube Music",
    5: "Lyrics.ovh",
    6: "ChartLyrics"
}

DEFAULT_SYNCED_SEQUENCE = [2, 3, 4]
DEFAULT_PLAIN_SEQUENCE = [1, 2, 3, 4, 5, 6]

# Fast mode uses only the fastest fetchers
FAST_MODE_SEQUENCE = [2, 3]  # LRCLIB and SimpMusic

async def fetch_with_timeout(api_name: str, fetcher, artist_name: str, song_title: str, timestamps: bool, timeout: int = 10):
    """Fetch with timeout protection and automatic retry on transient failures"""

    @retry(
        wait=wait_exponential(multiplier=0.5, min=1, max=4),
        stop=stop_after_attempt(2),
        retry=retry_if_exception_type(Exception),
        reraise=True
    )
    async def _fetch_with_retry():
        return await asyncio.wait_for(
            maybe_await(fetcher.fetch, artist_name, song_title, timestamps=timestamps),
            timeout=timeout
        )

    try:
        result = await _fetch_with_retry()
        # Validate result has actual lyrics
        if result and (not timestamps or result.get("hasTimestamps") or result.get("timed_lyrics") or result.get("timestamped")):
            return {"api": api_name, "result": result, "success": True}
        return {"api": api_name, "success": False, "reason": "no_results"}
    except asyncio.TimeoutError:
        return {"api": api_name, "success": False, "reason": "timeout"}
    except Exception as e:
        logger.error(f"{api_name} error: {str(e)}")
        return {"api": api_name, "success": False, "reason": str(e)}

async def fetch_lyrics_parallel(artist_name: str, song_title: str, timestamps: bool, fetcher_ids: list):
    """Fetch from multiple sources in parallel, return first success"""
    all_fetchers = {
        1: ("Genius", ALL_FETCHERS.get("genius")),
        2: ("LRCLIB", ALL_FETCHERS.get("lrclib")),
        3: ("SimpMusic", ALL_FETCHERS.get("simpmusic")),
        4: ("YouTube Music", ALL_FETCHERS.get("youtube")),
        5: ("Lyrics.ovh", ALL_FETCHERS.get("lyricsovh")),
        6: ("ChartLyrics", ALL_FETCHERS.get("chartlyrics")),
    }
    
    # Create tasks for all fetchers
    tasks = []
    
    for fetcher_id in fetcher_ids:
        if fetcher_id not in all_fetchers:
            continue
        api_name, fetcher = all_fetchers[fetcher_id]
        if not fetcher:
            continue
        # Create task explicitly to avoid coroutine issue
        task = asyncio.create_task(fetch_with_timeout(api_name, fetcher, artist_name, song_title, timestamps))
        tasks.append(task)
    
    # Race: return first successful result
    if not tasks:
        return None, []
    
    attempts = []
    pending = set(tasks)
    
    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        
        for task in done:
            result = await task
            attempts.append(result)
            if result["success"]:
                # Cancel remaining tasks
                for t in pending:
                    t.cancel()
                return result["result"], attempts
    
    return None, attempts

async def fetch_lyrics_controller(artist_name: str, song_title: str, timestamps: bool=False, pass_param: bool=False, sequence: str|None=None, fast_mode: bool=False):
    """Main controller - handles normal and fast parallel modes"""
    
    all_fetchers = {
        1: ("Genius", ALL_FETCHERS.get("genius")),
        2: ("LRCLIB", ALL_FETCHERS.get("lrclib")),
        3: ("SimpMusic", ALL_FETCHERS.get("simpmusic")),
        4: ("YouTube Music", ALL_FETCHERS.get("youtube")),
        5: ("Lyrics.ovh", ALL_FETCHERS.get("lyricsovh")),
        6: ("ChartLyrics", ALL_FETCHERS.get("chartlyrics")),
    }
    
    # Determine fetcher sequence
    if fast_mode:
        # Fast mode: parallel fetch from LRCLIB + SimpMusic only
        fetcher_ids = FAST_MODE_SEQUENCE
        logger.info(f"Fast mode enabled for {artist_name} - {song_title}")
    elif pass_param and sequence:
        try:
            fetcher_ids = [int(x) for x in sequence.split(",") if x.strip() != ""]
            if not fetcher_ids or not all(1 <= x <= 6 for x in fetcher_ids) or len(fetcher_ids) > 6 or len(fetcher_ids) != len(set(fetcher_ids)):
                return {
                    "status": "error",
                    "error": {
                        "message": "Invalid sequence: must be unique numbers between 1 and 6",
                        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                    }
                }
        except ValueError:
            return {
                "status": "error",
                "error": {
                    "message": "Invalid sequence format: must be comma-separated integers",
                    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                }
            }
    else:
        # Normal mode: sequential fetch with defaults
        fetcher_ids = DEFAULT_SYNCED_SEQUENCE if timestamps else DEFAULT_PLAIN_SEQUENCE
    
    # If fast mode or custom sequence with multiple fetchers, use parallel
    if fast_mode or (pass_param and sequence and len(fetcher_ids) > 1):
        result, attempts = await fetch_lyrics_parallel(artist_name, song_title, timestamps, fetcher_ids)
        
        # Validate result matches requested artist/song
        if result:
            validation = validate_and_filter_results(artist_name, song_title, attempts, threshold=0.75)
            
            if validation["has_valid_match"]:
                # Return the first valid result with validation info (no duplicate data)
                valid_result = validation["valid_results"][0]
                response = {
                    "status": "success",
                    "data": valid_result["result"]
                }
                # Only add validation if it's useful (i.e., if match isn't perfect)
                if valid_result["validation"]["artist_match"] < 1.0 or valid_result["validation"]["song_match"] < 1.0:
                    response["validation"] = valid_result["validation"]
                return response
            else:
                # All results failed validation
                logger.warning(f"No valid matches found for '{artist_name}' - '{song_title}' after validation")
                return {
                    "status": "error",
                    "error": {
                        "message": f"Found results but none matched '{song_title}' by '{artist_name}' (possible wrong song returned by API)",
                        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                    }
                }
        else:
            return {
                "status": "error",
                "error": {
                    "message": f"No lyrics found for '{song_title}' by '{artist_name}'",
                    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                }
            }
    
    # Normal sequential mode
    attempts = []
    for fetcher_id in fetcher_ids:
        api_name, fetcher = all_fetchers[fetcher_id]
        if not fetcher:
            attempts.append({"api": api_name, "status": "not_configured"})
            continue
        
        try:
            result = await maybe_await(fetcher.fetch, artist_name, song_title, timestamps=timestamps)
            if result and (not timestamps or result.get("hasTimestamps") or result.get("timed_lyrics") or result.get("timestamped")):
                # Validate result before returning
                validation = validate_and_filter_results(artist_name, song_title, [{"api": api_name, "result": result}], threshold=0.75)
                
                if validation["has_valid_match"]:
                    valid_result = validation["valid_results"][0]
                    return {
                        "status": "success",
                        "data": valid_result["result"]
                    }
                else:
                    # This result didn't match, continue to next fetcher
                    attempts.append({
                        "api": api_name,
                        "status": "validation_failed"
                    })
                    continue
            
            attempts.append({"api": api_name, "status": "no_results"})
        except Exception as e:
            logger.error(f"{api_name} error: {str(e)}")
            attempts.append({"api": api_name, "status": "error", "message": str(e)})
    
    return {
        "status": "error",
        "error": {
            "message": f"No lyrics found for '{song_title}' by '{artist_name}'",
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        }
    }