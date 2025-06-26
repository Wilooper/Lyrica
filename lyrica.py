from flask import Flask, request, jsonify
from flask_cors import CORS
from ytmusicapi import YTMusic
from lyricsgenius import Genius
import requests
import logging
import os
from datetime import datetime
import asyncio
import re
from bs4 import BeautifulSoup

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*", "allow_headers": ["Content-Type"], "expose_headers": ["Access-Control-Allow-Origin"]}})

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GENIUS_TOKEN = os.environ.get("GENIUS_TOKEN", "5weEv6dsQEI-_GKQCuc6ND5dOoPK1w4xxG9Ne46LhEBCaNSVOTtqU3K2BXC4hV4C")

def log_api_attempt(api_name, artist, song, success, message=None):
    """Log API attempts for debugging"""
    status = "SUCCESS" if success else "FAILED"
    log_message = f"{api_name} API attempt for '{artist} - {song}': {status}"
    if message:
        log_message += f" ({message})"
    logger.info(log_message)

async def fetch_lyrics_youtube(artist_name, song_title, timestamps=False):
    """Fetch lyrics from YouTube Music API"""
    try:
        logger.info(f"Attempting YouTube Music API for {artist_name} - {song_title}")
        ytmusic = YTMusic()
        search_query = f"{song_title} {artist_name}"
        search_results = ytmusic.search(query=search_query, filter="songs", limit=1)

        if not search_results:
            log_api_attempt("YouTube Music", artist_name, song_title, False, "No search results")
            return None

        video_id = search_results[0].get('videoId')
        if not video_id:
            log_api_attempt("YouTube Music", artist_name, song_title, False, "No videoId found")
            return None

        watch_playlist = ytmusic.get_watch_playlist(videoId=video_id)
        lyrics_browse_id = watch_playlist.get('lyrics')

        if not lyrics_browse_id:
            log_api_attempt("YouTube Music", artist_name, song_title, False, "No lyrics browseId")
            return None

        lyrics_data = ytmusic.get_lyrics(browseId=lyrics_browse_id, timestamps=timestamps)
        if not lyrics_data:
            log_api_attempt("YouTube Music", artist_name, song_title, False, "No lyrics data")
            return None

        # Standardize output to match other APIs
        if lyrics_data.get('hasTimestamps'):
            lyrics = "\n".join(line['text'] for line in lyrics_data['lyrics'])
            timed_lyrics = [
                {
                    "text": line['text'],
                    "start_time": line['start_time'],
                    "end_time": line['end_time'],
                    "id": line['id']
                } for line in lyrics_data['lyrics']
            ]
        else:
            lyrics = lyrics_data['lyrics']
            timed_lyrics = None

        log_api_attempt("YouTube Music", artist_name, song_title, True)
        result = {
            "source": "youtube_music",
            "artist": artist_name,
            "title": song_title,
            "lyrics": lyrics,
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        }
        if timed_lyrics:
            result["timed_lyrics"] = timed_lyrics
            result["hasTimestamps"] = True
        return result

    except Exception as e:
        logger.error(f"YouTube Music API error: {str(e)}")
        log_api_attempt("YouTube Music", artist_name, song_title, False, str(e))
        return None

def fetch_lyrics_genius(artist_name, song_title):
    try:
        logger.info(f"Attempting Genius API for {artist_name} - {song_title}")
        genius = Genius(GENIUS_TOKEN, skip_non_songs=True, remove_section_headers=True)
        song = genius.search_song(song_title, artist_name)
        
        if song and song.lyrics:
            log_api_attempt("Genius", artist_name, song_title, True)
            return {
                "source": "genius",
                "artist": song.artist,
                "title": song.title,
                "lyrics": song.lyrics,
                "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            }
        log_api_attempt("Genius", artist_name, song_title, False, "No lyrics found")
    except Exception as e:
        logger.error(f"Genius API error: {str(e)}")
        log_api_attempt("Genius", artist_name, song_title, False, str(e))
    return None

def fetch_lyrics_lyricsovh(artist_name, song_title):
    try:
        logger.info(f"Attempting Lyrics.ovh API for {artist_name} - {song_title}")
        url = f"https://api.lyrics.ovh/v1/{artist_name}/{song_title}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if "lyrics" in data and data["lyrics"].strip():
                log_api_attempt("Lyrics.ovh", artist_name, song_title, True)
                return {
                    "source": "lyrics.ovh",
                    "artist": artist_name,
                    "title": song_title,
                    "lyrics": data["lyrics"],
                    "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                }
        log_api_attempt("Lyrics.ovh", artist_name, song_title, False, "No lyrics or empty response")
    except Exception as e:
        logger.error(f"Lyrics.ovh API error: {str(e)}")
        log_api_attempt("Lyrics.ovh", artist_name, song_title, False, str(e))
    return None

def fetch_lyrics_chartlyrics(artist_name, song_title):
    try:
        logger.info(f"Attempting ChartLyrics API for {artist_name} - {song_title}")
        url = f"http://api.chartlyrics.com/apiv1.asmx/SearchLyricDirect?artist={artist_name}&song={song_title}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200 and "<Lyric>" in response.text:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(response.content)
            lyric = root.findtext('.//Lyric')
            if lyric and lyric.strip():
                log_api_attempt("ChartLyrics", artist_name, song_title, True)
                return {
                    "source": "chartlyrics",
                    "artist": artist_name,
                    "title": song_title,
                    "lyrics": lyric,
                    "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                }
        log_api_attempt("ChartLyrics", artist_name, song_title, False, "No lyrics found")
    except Exception as e:
        logger.error(f"ChartLyrics API error: {str(e)}")
        log_api_attempt("ChartLyrics", artist_name, song_title, False, str(e))
    return None

def fetch_lyrics_lyricsfreek(artist_name, song_title):
    try:
        logger.info(f"Attempting LyricsFreek for {artist_name} - {song_title}")
        search_artist = artist_name.lower().replace(" ", "-")
        search_title = song_title.lower().replace(" ", "-")
        url = f"https://www.lyricsfreek.com/{search_artist}/{search_title}-lyrics"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; LyricsFetcher/1.0)"
        }
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            lyrics_div = soup.find("div", {"class": "lyrics"})
            if lyrics_div:
                lyrics = lyrics_div.get_text(separator="\n").strip()
                lyrics = re.sub(r"\n*Submit Corrections.*", "", lyrics, flags=re.IGNORECASE | re.DOTALL).strip()
                if lyrics:
                    log_api_attempt("LyricsFreek", artist_name, song_title, True)
                    return {
                        "source": "lyricsfreek",
                        "artist": artist_name,
                        "title": song_title,
                        "lyrics": lyrics,
                        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                    }
        log_api_attempt("LyricsFreek", artist_name, song_title, False, "No lyrics found")
    except Exception as e:
        logger.error(f"LyricsFreek error: {str(e)}")
        log_api_attempt("LyricsFreek", artist_name, song_title, False, str(e))
    return None

async def fetch_lyrics(artist_name, song_title, timestamps=False):
    # List of API fetchers with their names for logging
    fetchers = [
        ("YouTube Music", lambda a, s: fetch_lyrics_youtube(a, s, timestamps)),
        ("Genius", fetch_lyrics_genius),
        ("Lyrics.ovh", fetch_lyrics_lyricsovh),
        ("ChartLyrics", fetch_lyrics_chartlyrics),
        ("LyricsFreek", fetch_lyrics_lyricsfreek)
    ]

    attempts = []
    for api_name, fetcher in fetchers:
        try:
            # Handle async fetcher (YouTube Music)
            if api_name == "YouTube Music":
                result = await fetcher(artist_name, song_title)
            else:
                result = fetcher(artist_name, song_title)
                
            if result:
                # Success - return the lyrics
                return {
                    "status": "success",
                    "data": result,
                    "attempts": attempts
                }
            attempts.append({"api": api_name, "status": "no_results"})
        except Exception as e:
            logger.error(f"{api_name} error: {str(e)}")
            attempts.append({"api": api_name, "status": "error", "message": str(e)})
    
    # If we get here, all APIs failed
    return {
        "status": "error",
        "error": {
            "message": f"No lyrics found for '{song_title}' by '{artist_name}'",
            "attempts": attempts
        },
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    }

@app.route('/')
def home():
    return jsonify({
        "api": "Lyrics Master API",
        "version": "1.2",
        "status": "active",
        "endpoints": {
            "lyrics": "/lyrics/?artist=ARTIST&song=SONG[&timestamps=true]"
        },
        "supported_sources": ["YouTube Music", "Genius", "Lyrics.ovh", "ChartLyrics", "LyricsFreek"],
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    })

@app.route('/lyrics/', methods=['GET'])
async def get_lyrics():
    artist = request.args.get('artist', '').strip()
    song = request.args.get('song', '').strip()
    timestamps = request.args.get('timestamps', 'false').lower() == 'true'
    
    if not artist or not song:
        return jsonify({
            "status": "error",
            "error": {
                "message": "Artist and song name are required",
                "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            }
        }), 400

    logger.info(f"Lyrics request received for {artist} - {song}")
    result = await fetch_lyrics(artist, song, timestamps)
    return jsonify(result)

@app.route('/favicon.ico')
def favicon():
    return '', 204

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=9999)
