from difflib import SequenceMatcher
import re
from src.logger import get_logger

logger = get_logger("validator")

def normalize_string(text: str) -> str:
    """Normalize string for comparison - remove special chars, extra spaces, lowercase"""
    if not text:
        return ""
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.lower().strip()

def get_similarity_ratio(str1: str, str2: str) -> float:
    """Calculate similarity ratio between two strings (0-1)"""
    str1 = normalize_string(str1)
    str2 = normalize_string(str2)
    if not str1 or not str2:
        return 0.0
    return SequenceMatcher(None, str1, str2).ratio()

def split_artists(artist_str: str) -> list:
    """Split artist string into individual normalized names"""
    if not artist_str:
        return []
    featuring_patterns = r'\s*(feat\.|ft\.|featuring|with|&|and)\s*'
    artist_str = re.sub(featuring_patterns, ', ', artist_str, flags=re.I)
    delimiters = r'\s*,\s*|\s*;\s*|\s*/\s*'
    return [normalize_string(a) for a in re.split(delimiters, artist_str) if a.strip()]

def extract_artist_song_from_result(result: dict) -> tuple:
    """Extract artist list and song title from result dict"""
    artist = (result.get("artist") or result.get("artists") or 
              result.get("artist_name") or result.get("trackArtist"))
    song = (result.get("song") or result.get("song_title") or 
            result.get("title") or result.get("name") or result.get("trackName"))
    
    if isinstance(artist, list):
        returned_artists = [normalize_string(a) for a in artist if a]
    elif isinstance(artist, str):
        returned_artists = split_artists(artist)
    else:
        returned_artists = []
    
    return returned_artists, normalize_string(str(song or ""))

def validate_lyrics_match(requested_artist: str, requested_song: str, result: dict, threshold: float = 0.5) -> dict:
    """
    ULTIMATE VALIDATOR:
    Passes if Requested Artist is found in:
    1. The Artist List (Individual check)
    2. The Full Artist String (Partial check)
    3. The Song Title (Featured check)
    """
    requested_artists = split_artists(requested_artist)
    normalized_requested_song = normalize_string(requested_song)
    returned_artists, returned_song = extract_artist_song_from_result(result)
    
    # Get the raw string version of returned artists for partial matching
    raw_returned_artists_str = " ".join(returned_artists)

    if not returned_artists or not returned_song:
        return {"valid": False, "reason": "Missing metadata"}

    # 1. Song Name Match (Required)
    song_similarity = get_similarity_ratio(normalized_requested_song, returned_song)
    
    # 2. Artist Match Logic
    found_match = False
    match_method = ""

    for req in requested_artists:
        # Check A: Direct similarity to any returned artist
        if any(get_similarity_ratio(req, ret) >= threshold for ret in returned_artists):
            found_match = True
            match_method = "Artist List"
            break
        
        # Check B: Name exists as a substring in the full artist string
        if len(req) > 3 and req in raw_returned_artists_str:
            found_match = True
            match_method = "Partial Artist String"
            break

        # Check C: Name exists in the Song Title (e.g. "Song (feat. Artist)")
        if len(req) > 3 and req in returned_song:
            found_match = True
            match_method = "Song Title"
            break

    if found_match and song_similarity >= threshold:
        logger.info(f"✓ Valid match ({match_method}): '{requested_artist}' - '{requested_song}'")
        return {
            "valid": True,
            "reason": f"Matched via {match_method}",
            "returned_artists": returned_artists,
            "returned_song": returned_song,
            "song_match": round(song_similarity, 3)
        }
    
    logger.warning(f"✗ Invalid match: '{requested_artist}' vs '{raw_returned_artists_str}' - '{returned_song}'")
    return {
        "valid": False,
        "reason": "Artist not found in metadata",
        "returned_artists": returned_artists,
        "returned_song": returned_song,
        "song_match": round(song_similarity, 3)
    }

def validate_and_filter_results(requested_artist: str, requested_song: str, attempts: list, threshold: float = 0.5) -> dict:
    valid_results = []
    invalid_results = []
    for attempt in attempts:
        if not isinstance(attempt, dict) or not attempt.get("success", True): continue
        if "result" in attempt and attempt["result"]:
            val = validate_lyrics_match(requested_artist, requested_song, attempt["result"], threshold)
            if val["valid"]:
                valid_results.append({"api": attempt.get("api"), "result": attempt["result"], "validation": val})
            else:
                invalid_results.append({"api": attempt.get("api"), "reason": val["reason"]})
    
    return {"has_valid_match": len(valid_results) > 0, "valid_results": valid_results, "all_failed": len(valid_results) == 0}
