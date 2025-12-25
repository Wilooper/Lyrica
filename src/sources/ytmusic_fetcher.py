import yt_dlp
from ytmusicapi import YTMusic
import logging

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/91.0.4472.124 Safari/537.36"
    )
}

# FIXED: Authenticated YTMusic (no more SSL handshake crashes)
try:
    ytmusic = YTMusic('header.json')
    logging.info("YTMusic loaded with headers_auth.json")
except:
    ytmusic = YTMusic()
    logging.warning("YTMusic fallback - generate headers_auth.json for stability")

logger = logging.getLogger("ytmusic_fetcher")

def search_songs(query, limit=20):
    results = ytmusic.search(query, filter="songs", limit=limit)
    songs = []
    for r in results:
        songs.append({
            "videoId": r.get('videoId'),
            "title": r.get('title'),
            "artist": ", ".join([a.get('name') for a in r.get('artists', [])]),
            "thumbnail": r.get('thumbnails', [{}])[-1].get('url') if r.get('thumbnails') else None,
            "duration": r.get('duration')
        })
    return songs

def get_trending(country="IN", limit=20):
    charts = ytmusic.get_charts(country=country)
    songs = []
    for r in charts.get('songs', {}).get('results', [])[:limit]:
        songs.append({
            "videoId": r.get('videoId'),
            "title": r.get('title'),
            "artist": r.get('artists', [{}])[0].get('name') if r.get('artists') else "",
            "thumbnail": r.get('thumbnails', [{}])[-1].get('url') if r.get('thumbnails') else None
        })
    return {"country": country, "results": songs}


def get_stream(video_id: str):
    """Get direct audio URL using yt-dlp (with browser-like UA) and ytmusic fallback."""
    # PRIORITY 1: yt-dlp (recommended)
    try:
        ydl_opts = {
            "format": "bestaudio/best[acodec!=none]/best",
            "quiet": True,
            "no_warnings": True,
            "http_headers": HEADERS,  # just UA, no cookies
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={video_id}",
                download=False,
            )
            duration = info.get("duration", 153)
            stream_url = info.get("url") or (info.get("formats") or [{}])[0].get("url")
            if stream_url:
                logger.info(f"yt-dlp stream found for {video_id}")
                return {"stream_url": stream_url, "duration": duration}
    except Exception as e:
        logger.warning(f"yt-dlp failed for {video_id}: {e}")

    # PRIORITY 2: ytmusic fallback (may still be null for some videos)
    info = None
    try:
        info = ytmusic.get_song(video_id)
        streaming = info.get("streamingData")
        if not streaming:
            logger.warning(f"No streamingData for {video_id}")
            duration = info.get("videoDetails", {}).get("lengthSeconds")
            return {"stream_url": None, "duration": duration}

        formats = streaming.get("adaptiveFormats", []) or []
        for f in formats:
            mime = f.get("mimeType", "")
            url = f.get("url")
            if url and ("audio/mp4" in mime or "audio/webm" in mime):
                duration = info.get("videoDetails", {}).get("lengthSeconds")
                logger.info(f"ytmusic audio stream for {video_id}")
                return {"stream_url": url, "duration": duration}

        # fallback: any format with direct url
        for f in formats:
            url = f.get("url")
            if url:
                duration = info.get("videoDetails", {}).get("lengthSeconds")
                logger.warning(f"Using non-audio format for {video_id}")
                return {"stream_url": url, "duration": duration}

    except Exception as e:
        logger.error(f"ytmusic fallback failed for {video_id}: {e}")

    # FINAL: no playable URL
    duration = (
        info.get("videoDetails", {}).get("lengthSeconds")
        if isinstance(info, dict)
        else 153
    )
    return {"stream_url": None, "duration": duration}




def get_suggestions(video_id, limit=20):
    try:
        watch = ytmusic.get_watch_playlist(video_id)
        tracks = watch.get('tracks', [])[:limit]
        songs = []
        for t in tracks:
            songs.append({
                "videoId": t.get('videoId'),
                "title": t.get('title'),
                "artist": t.get('artists', [{}])[0].get('name') if t.get('artists') else "",
                "thumbnail": t.get('thumbnail', [{}])[-1].get('url') if t.get('thumbnail') else None
            })
        return songs
    except Exception as e:
        logger.error(f"Suggestions error: {str(e)}")
        return []
