import asyncio
import re
import urllib.parse
from typing import Optional, Dict, Any
from functools import lru_cache
from datetime import datetime, timezone
import httpx
from src.logger import get_logger
from src.sources.base_fetcher import get_http_client

logger = get_logger("metadata_extractor")

# Free APIs (no auth required)
COVER_ART_API = "https://coverartarchive.org"
MUSICBRAINZ_API = "https://musicbrainz.org/ws/2"
WIKIPEDIA_API = "https://en.wikipedia.org/api/rest_v1"
ITUNES_API = "https://itunes.apple.com/search"

# Common browser headers
_HEADERS = {
    "User-Agent": "Lyrica/1.5.0 (https://github.com/thinkely/Lyrica)",
    "Accept": "application/json, text/html, */*",
}


async def get_musicbrainz_metadata(artist: str, song: str, client: Optional[httpx.AsyncClient] = None) -> Optional[Dict]:
    """Get metadata from MusicBrainz API (non-blocking async)."""
    http_cli = client or get_http_client()
    try:
        params = {
            "query": f'"{song}" AND artist:"{artist}"',
            "fmt": "json",
            "limit": 1,
            "inc": "tags+releases+artist-credits",
        }
        resp = await http_cli.get(
            f"{MUSICBRAINZ_API}/recording",
            params=params,
            headers=_HEADERS,
            timeout=5.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            recordings = data.get("recordings", [])
            if recordings:
                logger.info(f"Found MusicBrainz metadata: {artist} - {song}")
                return recordings[0]

        logger.debug(f"MusicBrainz: Track not found: {artist} - {song}")
        return None
    except Exception as e:
        logger.debug(f"MusicBrainz error: {e}")
        return None


async def get_wikipedia_summary(artist: str, song: str, client: Optional[httpx.AsyncClient] = None) -> Optional[Dict]:
    """Get summary from Wikipedia API (non-blocking async)."""
    http_cli = client or get_http_client()
    try:
        # Try "{song} (song)"
        page_title = urllib.parse.quote(f"{song} (song)")
        url = f"{WIKIPEDIA_API}/page/summary/{page_title}"
        resp = await http_cli.get(url, headers=_HEADERS, timeout=5.0)

        if resp.status_code == 200:
            data = resp.json()
            if "extract" in data:
                logger.info(f"Found Wikipedia summary for: {artist} - {song}")
                return {
                    "description": data.get("extract", ""),
                    "thumbnail": data.get("thumbnail", {}).get("source", ""),
                    "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
                }

        # Fallback: Try without "(song)"
        page_title_fallback = urllib.parse.quote(song)
        url_fallback = f"{WIKIPEDIA_API}/page/summary/{page_title_fallback}"
        resp_fb = await http_cli.get(url_fallback, headers=_HEADERS, timeout=5.0)
        if resp_fb.status_code == 200:
            data_fb = resp_fb.json()
            if "extract" in data_fb:
                logger.info(f"Found Wikipedia fallback summary for: {artist} - {song}")
                return {
                    "description": data_fb.get("extract", ""),
                    "thumbnail": data_fb.get("thumbnail", {}).get("source", ""),
                    "url": data_fb.get("content_urls", {}).get("desktop", {}).get("page", ""),
                }

        return None
    except Exception as e:
        logger.debug(f"Wikipedia error: {e}")
        return None


async def get_itunes_metadata(artist: str, song: str, client: Optional[httpx.AsyncClient] = None) -> Optional[Dict]:
    """Get metadata from iTunes Search API (non-blocking async)."""
    http_cli = client or get_http_client()
    try:
        params = {
            "term": f"{artist} {song}",
            "entity": "song",
            "limit": 1,
        }
        resp = await http_cli.get(ITUNES_API, params=params, headers=_HEADERS, timeout=5.0)
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results", [])
            if results:
                track = results[0]
                logger.info(f"Found iTunes metadata: {artist} - {song}")
                return {
                    "title": track.get("trackName", song),
                    "artist": track.get("artistName", artist),
                    "album": track.get("collectionName", ""),
                    "album_art": (
                        track.get("artworkUrl100", "").replace("100x100bb.jpg", "1200x1200bb.jpg")
                        if track.get("artworkUrl100") else ""
                    ),
                    "release_date": track.get("releaseDate", "")[:10] if track.get("releaseDate") else "",
                    "duration_ms": track.get("trackTimeMillis", 0),
                    "genre": track.get("primaryGenreName", ""),
                    "url": track.get("trackViewUrl", ""),
                }

        return None
    except Exception as e:
        logger.debug(f"iTunes error: {e}")
        return None


# Regex patterns for fast HTML parsing without bs4 overhead
_LASTFM_LISTENERS_RE = re.compile(r'data-analytics-label="listener_count"[^>]*>.*?<[a-zA-Z0-9_-]+[^>]*class="[^"]*metadata-display[^"]*"[^>]*>([^<]+)<', re.DOTALL)
_LASTFM_SCROBBLES_RE = re.compile(r'data-analytics-label="scrobble_count"[^>]*>.*?<[a-zA-Z0-9_-]+[^>]*class="[^"]*metadata-display[^"]*"[^>]*>([^<]+)<', re.DOTALL)
_LASTFM_TAGS_RE = re.compile(r'<a[^>]*href="[^"]*/tag/[^"]*"[^>]*>([^<]+)</a>', re.DOTALL)
_LASTFM_ALBUM_RE = re.compile(r'class="[^"]*header-metadata-title[^"]*"[^>]*><a[^>]*>([^<]+)</a>', re.DOTALL)


async def get_lastfm_metadata(artist: str, song: str, client: Optional[httpx.AsyncClient] = None) -> Optional[Dict]:
    """Scrape metadata from Last.fm using fast non-blocking regex extraction (no bs4)."""
    http_cli = client or get_http_client()
    try:
        url = f"https://www.last.fm/music/{urllib.parse.quote(artist)}/_/{urllib.parse.quote(song)}"
        resp = await http_cli.get(url, headers=_HEADERS, timeout=5.0)
        if resp.status_code == 200:
            html = resp.text

            # Extract listeners
            listeners = 0
            lm = _LASTFM_LISTENERS_RE.search(html)
            if lm:
                digits = re.sub(r"[^\d]", "", lm.group(1))
                if digits.isdigit():
                    listeners = int(digits)

            # Extract playcount (scrobbles)
            playcount = 0
            pm = _LASTFM_SCROBBLES_RE.search(html)
            if pm:
                digits = re.sub(r"[^\d]", "", pm.group(1))
                if digits.isdigit():
                    playcount = int(digits)

            # Extract tags
            tags = [t.strip() for t in _LASTFM_TAGS_RE.findall(html)[:7] if t.strip()]

            # Extract album
            am = _LASTFM_ALBUM_RE.search(html)
            album = am.group(1).strip() if am else ""

            if listeners or playcount or tags:
                logger.info(f"Found Last.fm scraped metadata: {artist} - {song}")
                return {
                    "playcount": playcount,
                    "listeners": listeners,
                    "tags": tags,
                    "album": album,
                    "url": url,
                }

        return None
    except Exception as e:
        logger.debug(f"Last.fm scrape error: {e}")
        return None


async def get_cover_art(mbid: str, client: Optional[httpx.AsyncClient] = None) -> Optional[str]:
    """Get album cover art from Cover Art Archive."""
    if not mbid:
        return None
    http_cli = client or get_http_client()
    try:
        resp = await http_cli.get(
            f"{COVER_ART_API}/release/{mbid}/front",
            headers=_HEADERS,
            timeout=5.0,
            follow_redirects=True,
        )
        if resp.status_code == 200:
            return f"{COVER_ART_API}/release/{mbid}/front"
        return None
    except Exception:
        return None


async def get_song_metadata_async(artist: str, song: str) -> Dict[str, Any]:
    """
    Get comprehensive metadata from multiple free APIs in parallel using asyncio.gather.
    Ultra-fast and 100% non-blocking.
    """
    try:
        metadata = {}
        sources_used = []

        # Run all 4 metadata requests concurrently via asyncio.gather
        mb_task = get_musicbrainz_metadata(artist, song)
        itunes_task = get_itunes_metadata(artist, song)
        lastfm_task = get_lastfm_metadata(artist, song)
        wiki_task = get_wikipedia_summary(artist, song)

        mb_data, itunes_data, lastfm_data, wiki_data = await asyncio.gather(
            mb_task, itunes_task, lastfm_task, wiki_task, return_exceptions=True
        )

        mb_data = mb_data if isinstance(mb_data, dict) else None
        itunes_data = itunes_data if isinstance(itunes_data, dict) else None
        lastfm_data = lastfm_data if isinstance(lastfm_data, dict) else None
        wiki_data = wiki_data if isinstance(wiki_data, dict) else None

        # 1. MusicBrainz
        if mb_data:
            sources_used.append("MusicBrainz")
            releases = mb_data.get("releases", [])
            release_title = release_date = release_id = ""
            if releases:
                release = releases[0]
                release_id = release.get("id", "")
                release_date = release.get("date", "")
                release_title = release.get("title", "")

            metadata.update({
                "title": mb_data.get("title", song),
                "musicbrainz_id": mb_data.get("id", ""),
                "release_id": release_id,
                "release_date": release_date,
                "release_title": release_title,
                "duration_ms": mb_data.get("length", 0),
                "tags": [tag.get("name") for tag in mb_data.get("tags", [])[:5] if tag.get("name")],
            })
            artist_credit = mb_data.get("artist-credit", [])
            metadata["artist"] = (
                artist_credit[0].get("artist", {}).get("name", artist)
                if artist_credit else artist
            )
            metadata["album"] = release_title

            if release_id:
                cover_art = await get_cover_art(release_id)
                if cover_art:
                    metadata["album_art"] = cover_art
                    sources_used.append("Cover Art Archive")

        # 2. iTunes
        if itunes_data:
            sources_used.append("iTunes")
            metadata["title"] = metadata.get("title") or itunes_data["title"]
            metadata["artist"] = metadata.get("artist") or itunes_data["artist"]
            metadata["album"] = metadata.get("album") or itunes_data["album"]
            metadata["release_date"] = metadata.get("release_date") or itunes_data["release_date"]
            metadata["duration_ms"] = metadata.get("duration_ms") or itunes_data["duration_ms"]
            if not metadata.get("album_art") and itunes_data.get("album_art"):
                metadata["album_art"] = itunes_data["album_art"]
            if not metadata.get("tags") and itunes_data.get("genre"):
                metadata["tags"] = [itunes_data["genre"]]
            metadata["itunes_url"] = itunes_data.get("url", "")

        # 3. Last.fm
        if lastfm_data:
            sources_used.append("Last.fm")
            metadata["playcount"] = lastfm_data.get("playcount", 0)
            metadata["listeners"] = lastfm_data.get("listeners", 0)
            if not metadata.get("tags") and lastfm_data.get("tags"):
                metadata["tags"] = lastfm_data["tags"]
            if not metadata.get("album") and lastfm_data.get("album"):
                metadata["album"] = lastfm_data["album"]
            metadata["lastfm_url"] = lastfm_data.get("url", "")

        # 4. Wikipedia
        if wiki_data:
            sources_used.append("Wikipedia")
            metadata.update({
                "description": wiki_data.get("description", ""),
                "wiki_thumbnail": wiki_data.get("thumbnail", ""),
                "wiki_url": wiki_data.get("url", ""),
            })

        if not metadata:
            return {
                "success": False,
                "error": f"No metadata found for '{song}' by '{artist}'",
                "sources": []
            }

        # Popularity score 0-100
        listeners = metadata.get("listeners", 0)
        metadata["popularity"] = min(100, max(0, int((listeners / 10000) ** 0.5 * 10))) if listeners else 0

        return {"success": True, "metadata": metadata, "sources": sources_used}

    except Exception as e:
        logger.error(f"Metadata retrieval error: {e}")
        return {"success": False, "error": str(e), "sources": []}


def format_metadata(metadata: Dict) -> Dict:
    """Format metadata for API response."""
    try:
        duration_ms = metadata.get("duration_ms", 0)
        duration_sec = duration_ms // 1000 if duration_ms else 0
        minutes = duration_sec // 60
        seconds = duration_sec % 60

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
        logger.error(f"Metadata formatting error: {e}")
        return {}


async def enhance_lyrics_with_metadata(lyrics_response: Dict, artist: str, song: str) -> Dict:
    """Add metadata to lyrics response (async)."""
    try:
        metadata_result = await get_song_metadata_async(artist, song)
        if metadata_result.get("success"):
            formatted = format_metadata(metadata_result["metadata"])
            lyrics_response["metadata"] = formatted
        else:
            lyrics_response["metadata"] = {
                "error": metadata_result.get("error", "Could not fetch metadata"),
                "success": False
            }
        return lyrics_response
    except Exception as e:
        logger.error(f"Enhance lyrics error: {e}")
        lyrics_response["metadata"] = {
            "error": str(e),
            "success": False
        }
        return lyrics_response


async def get_metadata_only(artist: str, song: str) -> Dict:
    """Get only metadata without lyrics (async)."""
    try:
        metadata_result = await get_song_metadata_async(artist, song)
        now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        if metadata_result.get("success"):
            formatted = format_metadata(metadata_result["metadata"])
            return {
                "status": "success",
                "metadata": formatted,
                "sources": metadata_result.get("sources", []),
                "timestamp": now_ts
            }
        else:
            return {
                "status": "error",
                "error": metadata_result.get("error", "Metadata fetch failed"),
                "sources": [],
                "timestamp": now_ts
            }
    except Exception as e:
        logger.error(f"Get metadata only error: {e}")
        return {
            "status": "error",
            "error": str(e),
            "sources": [],
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        }


# Synchronous wrapper for backward compatibility
def get_song_metadata(artist: str, song: str) -> Dict:
    """Sync wrapper for get_song_metadata_async."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
            return loop.run_until_complete(get_song_metadata_async(artist, song))
        return loop.run_until_complete(get_song_metadata_async(artist, song))
    except Exception:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(get_song_metadata_async(artist, song))
        finally:
            loop.close()