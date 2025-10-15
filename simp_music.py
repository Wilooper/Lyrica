import requests
import logging

logger = logging.getLogger(__name__)

API_BASE = "https://api-lyrics.simpmusic.org/v1"

def search_song(title: str, artist: str = None):
    """Search for a song using SimpMusic API"""
    try:
        params = {"q": title}
        resp = requests.get(f"{API_BASE}/search", params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"SimpMusic search error: {str(e)}")
        return None

def get_lyrics(video_id: str):
    """Fetch lyrics using SimpMusic API by video ID"""
    try:
        resp = requests.get(f"{API_BASE}/{video_id}", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"SimpMusic lyrics fetch error: {str(e)}")
        return None

def fetch_lyrics_simpmusic(artist_name: str, song_title: str):
    """
    Main function to get lyrics (timestamped + plain if available)
    Compatible with Lyrica format
    """
    logger.info(f"Attempting SimpMusic API for {artist_name} - {song_title}")

    search_data = search_song(song_title, artist_name)
    if not search_data:
        return None

    results = search_data.get("data") if isinstance(search_data, dict) else search_data
    if not results:
        return None

    first = results[0]
    video_id = first.get("videoId") or first.get("id")
    if not video_id:
        return None

    lyric_data = get_lyrics(video_id)
    if not lyric_data:
        return None

    d = lyric_data.get("data")
    if isinstance(d, list) and len(d) > 0:
        d = d[0]
    if not isinstance(d, dict):
        return None

    return {
        "source": "simpmusic",
        "artist": first.get("artistName") or artist_name,
        "title": first.get("title") or song_title,
        "lyrics": d.get("plainLyrics") or d.get("lyrics") or None,
        "timestamped": d.get("syncedLyrics") or d.get("lrc") or None
    }
