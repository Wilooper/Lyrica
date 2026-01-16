import requests
import logging
from typing import Optional, Dict
from functools import lru_cache
from datetime import datetime
from bs4 import BeautifulSoup

logger = logging.getLogger("metadata_extractor")

# APIs we'll use (all free, no auth required)
COVER_ART_API = "https://coverartarchive.org"
MUSICBRAINZ_API = "https://musicbrainz.org/ws/2"
WIKIPEDIA_API = "https://en.wikipedia.org/api/rest_v1"
ITUNES_API = "https://itunes.apple.com/search"

def get_musicbrainz_metadata(artist: str, song: str) -> Optional[Dict]:
    """
    Get metadata from MusicBrainz API (free, no auth required)
    Returns: MBID, recording info, release info, tags, etc.
    """
    try:
        # Search for recording with additional includes for more data
        headers = {
            "User-Agent": "Lyrica/1.0 (lyrics API)"
        }
        params = {
            "query": f'"{song}" AND artist:"{artist}"',
            "fmt": "json",
            "limit": 1,
            "inc": "tags+releases+artist-credits"  # Enhanced: Include tags and artist credits
        }
        
        response = requests.get(
            f"{MUSICBRAINZ_API}/recording",
            params=params,
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("recordings") and len(data["recordings"]) > 0:
                recording = data["recordings"][0]
                logger.info(f"Found MusicBrainz metadata: {artist} - {song}")
                return recording
        
        logger.warning(f"MusicBrainz: Track not found: {artist} - {song}")
        return None
    except Exception as e:
        logger.error(f"MusicBrainz error: {str(e)}")
        return None

def get_wikipedia_summary(artist: str, song: str) -> Optional[Dict]:
    """
    Get summary from Wikipedia API (free, no auth required)
    Searches for the song page and returns extract, thumbnail, etc.
    """
    try:
        # Construct potential page title (e.g., "Song Title (song)")
        page_title = f"{song} (song)"
        url = f"{WIKIPEDIA_API}/page/summary/{requests.utils.quote(page_title)}"
        
        headers = {
            "User-Agent": "Lyrica/1.0 (lyrics API)"
        }
        
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if "extract" in data:
                logger.info(f"Found Wikipedia summary for: {artist} - {song}")
                return {
                    "description": data.get("extract", ""),
                    "thumbnail": data.get("thumbnail", {}).get("source", ""),
                    "url": data.get("content_urls", {}).get("desktop", {}).get("page", "")
                }
        
        # Fallback: Try without "(song)"
        page_title = song
        url = f"{WIKIPEDIA_API}/page/summary/{requests.utils.quote(page_title)}"
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if "extract" in data:
                logger.info(f"Found Wikipedia fallback summary for: {artist} - {song}")
                return {
                    "description": data.get("extract", ""),
                    "thumbnail": data.get("thumbnail", {}).get("source", ""),
                    "url": data.get("content_urls", {}).get("desktop", {}).get("page", "")
                }
        
        logger.warning(f"Wikipedia: Page not found for {artist} - {song}")
        return None
    except Exception as e:
        logger.error(f"Wikipedia error: {str(e)}")
        return None

def get_itunes_metadata(artist: str, song: str) -> Optional[Dict]:
    """
    Get metadata from iTunes Search API (free, no auth required)
    Returns: album, artwork, release date, duration, genre, etc.
    """
    try:
        term = f"{artist} {song}"
        params = {
            "term": term,
            "entity": "song",
            "limit": 1
        }
        response = requests.get(ITUNES_API, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("resultCount", 0) > 0:
                track = data["results"][0]
                logger.info(f"Found iTunes metadata: {artist} - {song}")
                return {
                    "title": track.get("trackName", song),
                    "artist": track.get("artistName", artist),
                    "album": track.get("collectionName", ""),
                    "album_art": track.get("artworkUrl100", "").replace("100x100bb.jpg", "1200x1200bb.jpg") if track.get("artworkUrl100") else "",
                    "release_date": track.get("releaseDate", "")[:10] if track.get("releaseDate") else "",
                    "duration_ms": track.get("trackTimeMillis", 0),
                    "genre": track.get("primaryGenreName", ""),
                    "url": track.get("trackViewUrl", "")
                }
        
        logger.warning(f"iTunes: Track not found: {artist} - {song}")
        return None
    except Exception as e:
        logger.error(f"iTunes error: {str(e)}")
        return None

def get_lastfm_metadata(artist: str, song: str) -> Optional[Dict]:
    """
    Scrape metadata from Last.fm public page (no API key required)
    Returns: playcount, listeners, tags, etc.
    """
    try:
        url = f"https://www.last.fm/music/{requests.utils.quote(artist)}/_/{requests.utils.quote(song)}"
        headers = {"User-Agent": "Lyrica/1.0 (lyrics API)"}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract listeners
            listeners_elem = soup.select_one('li[data-analytics-label="listener_count"] .metadata-display')
            listeners = 0
            if listeners_elem:
                listeners_text = listeners_elem.text.strip().replace(',', '')
                if listeners_text.isdigit():
                    listeners = int(listeners_text)
            
            # Extract playcount (scrobbles)
            playcount_elem = soup.select_one('li[data-analytics-label="scrobble_count"] .metadata-display')
            playcount = 0
            if playcount_elem:
                playcount_text = playcount_elem.text.strip().replace(',', '')
                if playcount_text.isdigit():
                    playcount = int(playcount_text)
            
            # Extract tags
            tags = []
            tag_elements = soup.select('.tags-list--global a')
            for tag in tag_elements[:7]:
                tags.append(tag.text.strip())
            
            # Extract album if available
            album_elem = soup.select_one('.header-metadata-title a')
            album = album_elem.text.strip() if album_elem else ""
            
            if listeners or playcount or tags:
                logger.info(f"Found Last.fm scraped metadata: {artist} - {song}")
                return {
                    "playcount": playcount,
                    "listeners": listeners,
                    "tags": tags,
                    "album": album,
                    "url": url
                }
        
        logger.warning(f"Last.fm: Track not found: {artist} - {song}")
        return None
    except Exception as e:
        logger.error(f"Last.fm scrape error: {str(e)}")
        return None

def get_cover_art(mbid: str) -> Optional[str]:
    """
    Get album cover art from Cover Art Archive (free)
    MBID should come from MusicBrainz
    """
    try:
        if not mbid:
            return None
        
        response = requests.get(
            f"{COVER_ART_API}/release/{mbid}/front",
            timeout=5,
            allow_redirects=True
        )
        
        if response.status_code == 200:
            logger.info(f"Found cover art for MBID: {mbid}")
            return f"{COVER_ART_API}/release/{mbid}/front"
        
        return None
    except Exception as e:
        logger.error(f"Cover Art error: {str(e)}")
        return None

@lru_cache(maxsize=500)
def get_song_metadata(artist: str, song: str) -> Dict:
    """
    Get comprehensive metadata from multiple free APIs
    
    Args:
        artist: Artist name
        song: Song title
    
    Returns:
        {
            "success": bool,
            "metadata": {...},
            "sources": [list of APIs used]
        }
    """
    try:
        metadata = {}
        sources_used = []
        
        # 1. Fetch from MusicBrainz for core info
        mb_data = get_musicbrainz_metadata(artist, song)
        if mb_data:
            sources_used.append("MusicBrainz")
            
            # Extract release info
            releases = mb_data.get("releases", [])
            release_title = ""
            release_date = ""
            release_id = ""
            if releases:
                release = releases[0]
                release_id = release.get("id", "")
                release_date = release.get("date", "")
                release_title = release.get("title", "")

            # Populate fields from MusicBrainz
            metadata.update({
                "title": mb_data.get("title", song),
                "musicbrainz_id": mb_data.get("id", ""),
                "release_id": release_id,
                "release_date": release_date,
                "release_title": release_title,
                "duration_ms": mb_data.get("length", 0),
                "tags": [tag.get("name") for tag in mb_data.get("tags", [])[:5]],
            })

            # Extract artist
            artist_credit = mb_data.get("artist-credit", [])
            if artist_credit:
                metadata["artist"] = artist_credit[0].get("artist", {}).get("name", artist)
            else:
                metadata["artist"] = artist

            # Set album
            metadata["album"] = release_title

            # Try to get cover art
            release_mbid = release_id
            cover_art = get_cover_art(release_mbid)
            if cover_art:
                metadata["album_art"] = cover_art
                sources_used.append("Cover Art Archive")
        
        # 2. Fetch from iTunes for additional details
        itunes_data = get_itunes_metadata(artist, song)
        if itunes_data:
            sources_used.append("iTunes")
            metadata["title"] = metadata.get("title") or itunes_data["title"]
            metadata["artist"] = itunes_data["artist"]  # Prefer iTunes for full artist name
            metadata["album"] = metadata.get("album") or itunes_data["album"]
            metadata["release_date"] = metadata.get("release_date") or itunes_data["release_date"]
            metadata["duration_ms"] = metadata.get("duration_ms") or itunes_data["duration_ms"]
            if not metadata.get("album_art"):
                metadata["album_art"] = itunes_data["album_art"]
            if not metadata.get("tags") and itunes_data["genre"]:
                metadata["tags"] = [itunes_data["genre"]]
            metadata["itunes_url"] = itunes_data["url"]
        
        # 3. Scrape from Last.fm for popularity metrics and tags
        lastfm_data = get_lastfm_metadata(artist, song)
        if lastfm_data:
            sources_used.append("Last.fm")
            metadata["playcount"] = lastfm_data.get("playcount", 0)
            metadata["listeners"] = lastfm_data.get("listeners", 0)
            if not metadata.get("tags"):
                metadata["tags"] = lastfm_data.get("tags", [])
            if not metadata.get("album"):
                metadata["album"] = lastfm_data.get("album", "")
            metadata["lastfm_url"] = lastfm_data["url"]
        
        # 4. Fetch from Wikipedia for description and additional visuals
        wiki_data = get_wikipedia_summary(artist, song)
        if wiki_data:
            sources_used.append("Wikipedia")
            metadata.update({
                "description": wiki_data.get("description", ""),
                "wiki_thumbnail": wiki_data.get("thumbnail", ""),
                "wiki_url": wiki_data.get("url", "")
            })
        
        if not metadata:
            return {
                "success": False,
                "error": f"No metadata found for '{song}' by '{artist}'",
                "sources": []
            }
        
        # Calculate popularity score (0-100) from listeners if available
        listeners = metadata.get("listeners", 0)
        popularity = min(100, max(0, int((listeners / 10000) ** 0.5 * 10))) if listeners else 0  # Adjusted formula for better scaling
        metadata["popularity"] = popularity
        
        return {
            "success": True,
            "metadata": metadata,
            "sources": sources_used
        }
    
    except Exception as e:
        logger.error(f"Metadata retrieval error: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "sources": []
        }

def format_metadata(metadata: Dict) -> Dict:
    """
    Format metadata for API response
    
    Args:
        metadata: Raw metadata dict
    
    Returns:
        Formatted metadata with human-readable fields
    """
    try:
        # Convert milliseconds to seconds and formatted time
        duration_ms = metadata.get("duration_ms", 0)
        duration_sec = duration_ms // 1000 if duration_ms else 0
        minutes = duration_sec // 60
        seconds = duration_sec % 60
        
        # Parse release date
        release_date = metadata.get("release_date", "")
        release_year = release_date.split("-")[0] if release_date else ""
        
        return {
            "title": metadata.get("title", ""),
            "artist": metadata.get("artist", ""),
            "album": metadata.get("album", metadata.get("release_title", "")),
            "album_art": metadata.get("album_art", ""),
            "description": metadata.get("description", ""),
            "wiki_thumbnail": metadata.get("wiki_thumbnail", ""),
            "release_date": release_date,
            "release_year": int(release_year) if release_year.isdigit() else None,
            "duration": {
                "ms": duration_ms,
                "seconds": duration_sec,
                "formatted": f"{minutes}:{seconds:02d}" if duration_sec > 0 else "Unknown"
            },
            "popularity": metadata.get("popularity", 0),
            "playcount": metadata.get("playcount", 0),
            "listeners": metadata.get("listeners", 0),
            "tags": metadata.get("tags", []),
            "links": {
                "musicbrainz": f"https://musicbrainz.org/recording/{metadata.get('musicbrainz_id', '')}" if metadata.get("musicbrainz_id") else "",
                "lastfm": metadata.get("lastfm_url", ""),
                "itunes": metadata.get("itunes_url", ""),
                "wikipedia": metadata.get("wiki_url", "")
            },
            "musicbrainz_id": metadata.get("musicbrainz_id", ""),
            "release_id": metadata.get("release_id", "")
        }
    except Exception as e:
        logger.error(f"Metadata formatting error: {str(e)}")
        return {}

def enhance_lyrics_with_metadata(lyrics_response: Dict, artist: str, song: str) -> Dict:
    """
    Add metadata to lyrics response
    
    Args:
        lyrics_response: Original lyrics API response
        artist: Artist name
        song: Song title
    
    Returns:
        Enhanced response with metadata section
    """
    try:
        metadata_result = get_song_metadata(artist, song)
        
        if metadata_result["success"]:
            formatted = format_metadata(metadata_result["metadata"])
            lyrics_response["metadata"] = formatted
        else:
            lyrics_response["metadata"] = {
                "error": metadata_result.get("error", "Could not fetch metadata"),
                "success": False
            }
        
        return lyrics_response
    except Exception as e:
        logger.error(f"Enhance lyrics error: {str(e)}")
        lyrics_response["metadata"] = {
            "error": str(e),
            "success": False
        }
        return lyrics_response

def get_metadata_only(artist: str, song: str) -> Dict:
    """
    Get only metadata without lyrics
    
    Args:
        artist: Artist name
        song: Song title
    
    Returns:
        {
            "status": "success" | "error",
            "metadata": {...},
            "sources": [list of APIs used],
            "timestamp": str
        }
    """
    try:
        metadata_result = get_song_metadata(artist, song)
        
        if metadata_result["success"]:
            formatted = format_metadata(metadata_result["metadata"])
            return {
                "status": "success",
                "metadata": formatted,
                "sources": metadata_result["sources"],
                "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            }
        else:
            return {
                "status": "error",
                "error": metadata_result.get("error", "Metadata fetch failed"),
                "sources": [],
                "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            }
    except Exception as e:
        logger.error(f"Get metadata only error: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "sources": [],
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        }