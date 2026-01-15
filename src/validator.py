from difflib import SequenceMatcher
import re
from src.logger import get_logger

logger = get_logger("validator")

def normalize_string(text: str) -> str:
    """Normalize string for comparison - remove special chars, extra spaces, lowercase"""
    if not text:
        return ""
    # Remove special characters and extra spaces
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.lower().strip()

def get_similarity_ratio(str1: str, str2: str) -> float:
    """Calculate similarity ratio between two strings (0-1)"""
    str1 = normalize_string(str1)
    str2 = normalize_string(str2)
    
    if not str1 or not str2:
        return 0.0
    
    matcher = SequenceMatcher(None, str1, str2)
    return round(matcher.ratio(), 3)

def extract_artist_song_from_result(result: dict) -> tuple:
    """Extract artist and song title from different fetcher formats"""
    artist = None
    song = None
    
    # Try different field names used by different fetchers
    artist = (
        result.get("artist") or 
        result.get("artists") or 
        result.get("artist_name") or
        result.get("trackArtist")
    )
    
    song = (
        result.get("song") or
        result.get("song_title") or
        result.get("title") or
        result.get("name") or
        result.get("trackName")
    )
    
    # Handle artist as list
    if isinstance(artist, list) and artist:
        artist = artist[0]
    
    return str(artist or ""), str(song or "")

def validate_lyrics_match(requested_artist: str, requested_song: str, result: dict, threshold: float = 0.75) -> dict:
    """
    Validate if returned lyrics match the requested artist and song.
    
    Args:
        requested_artist: User's requested artist
        requested_song: User's requested song
        result: API response containing lyrics
        threshold: Minimum similarity ratio (0.75 = 75%)
    
    Returns:
        {
            "valid": bool,
            "artist_match": float (0-1),
            "song_match": float (0-1),
            "reason": str,
            "returned_artist": str,
            "returned_song": str
        }
    """
    
    returned_artist, returned_song = extract_artist_song_from_result(result)
    
    if not returned_artist or not returned_song:
        return {
            "valid": False,
            "artist_match": 0.0,
            "song_match": 0.0,
            "reason": "Missing artist or song info in result",
            "returned_artist": returned_artist,
            "returned_song": returned_song
        }
    
    # Calculate similarity
    artist_similarity = get_similarity_ratio(requested_artist, returned_artist)
    song_similarity = get_similarity_ratio(requested_song, returned_song)
    
    # Both must meet threshold
    if artist_similarity >= threshold and song_similarity >= threshold:
        logger.info(
            f"✓ Valid match: '{requested_artist}' - '{requested_song}' "
            f"(artist: {artist_similarity:.2%}, song: {song_similarity:.2%})"
        )
        return {
            "valid": True,
            "artist_match": artist_similarity,
            "song_match": song_similarity,
            "reason": "Match confirmed",
            "returned_artist": returned_artist,
            "returned_song": returned_song
        }
    
    # Determine which failed
    reason = ""
    if artist_similarity < threshold:
        reason = f"Artist mismatch (similarity: {artist_similarity:.2%})"
    if song_similarity < threshold:
        reason += f"{',' if reason else ''}Song mismatch (similarity: {song_similarity:.2%})"
    
    logger.warning(
        f"✗ Invalid match: '{requested_artist}' - '{requested_song}' "
        f"vs '{returned_artist}' - '{returned_song}' (artist: {artist_similarity:.2%}, song: {song_similarity:.2%})"
    )
    
    return {
        "valid": False,
        "artist_match": artist_similarity,
        "song_match": song_similarity,
        "reason": reason,
        "returned_artist": returned_artist,
        "returned_song": returned_song
    }

def validate_and_filter_results(requested_artist: str, requested_song: str, attempts: list, threshold: float = 0.75) -> dict:
    """
    Filter attempts and return only validated matches.
    
    Args:
        requested_artist: User's requested artist
        requested_song: User's requested song
        attempts: List of API attempt results from fetch_lyrics_controller
        threshold: Minimum similarity ratio
    
    Returns:
        {
            "has_valid_match": bool,
            "valid_results": [list of valid results with validation data],
            "invalid_results": [list of invalid results with reasons],
            "all_failed": bool
        }
    """
    valid_results = []
    invalid_results = []
    
    for attempt in attempts:
        if not isinstance(attempt, dict):
            continue
        
        # Skip failed attempts
        if attempt.get("success") == False:
            invalid_results.append({
                "api": attempt.get("api"),
                "reason": attempt.get("reason", "No results"),
                "validated": False
            })
            continue
        
        # If attempt has result data, validate it
        if "result" in attempt and attempt["result"]:
            validation = validate_lyrics_match(
                requested_artist, 
                requested_song, 
                attempt["result"],
                threshold
            )
            
            if validation["valid"]:
                valid_results.append({
                    "api": attempt.get("api"),
                    "result": attempt["result"],
                    "validation": validation
                })
            else:
                invalid_results.append({
                    "api": attempt.get("api"),
                    "validation": validation,
                    "reason": validation["reason"],
                    "validated": False
                })
    
    return {
        "has_valid_match": len(valid_results) > 0,
        "valid_results": valid_results,
        "invalid_results": invalid_results,
        "all_failed": len(valid_results) == 0
    }