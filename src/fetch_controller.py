from datetime import datetime, timezone
from src.logger import get_logger
from src.utils import maybe_await
from src.sources import ALL_FETCHERS
import time
import logging
from requests.exceptions import ConnectionError, RequestException
from urllib3.exceptions import ProtocolError

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
DEFAULT_PLAIN_SEQUENCE = [1, 2, 3, 4, 5,6]

async def fetch_lyrics_controller(artist_name: str, song_title: str, timestamps: bool=False, pass_param: bool=False, sequence: str|None=None):
    attempts = []
    
    # Build fetcher_list according to sequence or defaults
    all_fetchers = {
        1: ("Genius", ALL_FETCHERS.get("genius")),
        2: ("LRCLIB", ALL_FETCHERS.get("lrclib")),
        3: ("SimpMusic", ALL_FETCHERS.get("simpmusic")),
        4: ("YouTube Music", ALL_FETCHERS.get("youtube")),
        5: ("Lyrics.ovh", ALL_FETCHERS.get("lyricsovh")),
        6: ("ChartLyrics", ALL_FETCHERS.get("chartlyrics")),
    }
    
    if pass_param and sequence:
        try:
            seq_list = [int(x) for x in sequence.split(",") if x.strip() != ""]
            if not seq_list or not all(1 <= x <= 6 for x in seq_list) or len(seq_list) > 6 or len(seq_list) != len(set(seq_list)):
                return {"status":"error","error":{"message":"Invalid sequence: must be unique numbers between 1 and 6","timestamp":datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")}}
            fetcher_order = [(all_fetchers[num][0], all_fetchers[num][1]) for num in seq_list]
        except ValueError:
            return {"status":"error","error":{"message":"Invalid sequence format: must be comma-separated integers","timestamp":datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")}}
    else:
        order = DEFAULT_SYNCED_SEQUENCE if timestamps else DEFAULT_PLAIN_SEQUENCE
        fetcher_order = [(all_fetchers[num][0], all_fetchers[num][1]) for num in order]
    
    for api_name, fetcher in fetcher_order:
        if not fetcher:
            attempts.append({"api": api_name, "status": "not_configured"})
            continue
        
        try:
            result = await maybe_await(fetcher.fetch, artist_name, song_title, timestamps=timestamps)
            # If result present and (if timestamps requested ensure has timestamps)
            if result and (not timestamps or result.get("hasTimestamps") or result.get("timed_lyrics") or result.get("timestamped")):
                return {"status":"success","data":result,"attempts":attempts}
            attempts.append({"api": api_name, "status": "no_results"})
        except Exception as e:
            logger.error(f"{api_name} error: {str(e)}")
            attempts.append({"api": api_name, "status": "error", "message": str(e)})
    
    return {"status":"error","error":{"message":f"No lyrics found for '{song_title}' by '{artist_name}'","timestamp":datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")}}

