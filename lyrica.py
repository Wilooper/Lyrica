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
import inspect

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*", "allow_headers": ["Content-Type"], "expose_headers": ["Access-Control-Allow-Origin"]}})

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GENIUS_TOKEN = os.environ.get("GENIUS_TOKEN", "YOUR_GENIUS_API_KEY_HERE")
LRCLIB_API_URL = "https://lrclib.net/api/get"

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

def fetch_lyrics_lrclib(artist_name, song_title, timestamps=True):
    try:
        logger.info(f"Attempting LRCLIB API for {artist_name} - {song_title}")
        search_url = "https://lrclib.net/api/search"
        params = {
            "track_name": song_title,
            "artist_name": artist_name
        }
        search_resp = requests.get(search_url, params=params, timeout=10)
        if search_resp.status_code != 200:
            log_api_attempt("LRCLIB", artist_name, song_title, False, "Failed to search LRCLIB")
            return None
        
        results = search_resp.json()
        if not results:
            log_api_attempt("LRCLIB", artist_name, song_title, False, "Track not found")
            return None

        # Get the first result's info
        track = results[0]
        # Query the /api/get endpoint with full signature
        get_params = {
            "track_name": track["trackName"],
            "artist_name": track["artistName"],
            "album_name": track["albumName"],
            "duration": track["duration"]
        }
        get_resp = requests.get(LRCLIB_API_URL, params=get_params, timeout=10)
        if get_resp.status_code != 200:
            log_api_attempt("LRCLIB", artist_name, song_title, False, "Lyrics not found")
            return None

        data = get_resp.json()
        lyrics = data["syncedLyrics"] if timestamps else data["plainLyrics"]
        if not lyrics:
            log_api_attempt("LRCLIB", artist_name, song_title, False, "No lyrics available")
            return None

        result = {
            "source": "lrclib",
            "artist": data["artistName"],
            "title": data["trackName"],
            "album": data["albumName"],
            "duration": data["duration"],
            "instrumental": data.get("instrumental", False),
            "lyrics": lyrics,
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        }
        if timestamps and data["syncedLyrics"]:
            # Parse synced lyrics into timed_lyrics format
            timed_lyrics = []
            for line in data["syncedLyrics"].split("\n"):
                match = re.match(r"\[(\d{2}:\d{2}\.\d{2})\](.*)", line)
                if match:
                    time_str, text = match.groups()
                    # Convert MM:SS.mm to milliseconds
                    minutes, seconds = map(float, time_str.split(":"))
                    start_time = int((minutes * 60 + seconds) * 1000)
                    timed_lyrics.append({
                        "text": text.strip(),
                        "start_time": start_time,
                        "end_time": None,  # LRCLIB doesn't provide end times
                        "id": f"lrc_{len(timed_lyrics)}"
                    })
            result["timed_lyrics"] = timed_lyrics
            result["hasTimestamps"] = True

        log_api_attempt("LRCLIB", artist_name, song_title, True)
        return result

    except Exception as e:
        logger.error(f"LRCLIB API error: {str(e)}")
        log_api_attempt("LRCLIB", artist_name, song_title, False, str(e))
        return None

async def maybe_await(func, *args, **kwargs):
    result = func(*args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result

async def fetch_lyrics(artist_name, song_title, timestamps=False, pass_param=False, sequence=None):
    attempts = []
    
    # Define all available fetchers with their corresponding numbers
    all_fetchers = {
        1: ("Genius", lambda a, s, timestamps=timestamps: fetch_lyrics_genius(a, s)),
        2: ("LRCLIB", lambda a, s, timestamps=timestamps: fetch_lyrics_lrclib(a, s, timestamps)),
        3: ("YouTube Music", lambda a, s, timestamps=timestamps: fetch_lyrics_youtube(a, s, timestamps)),
        4: ("Lyrics.ovh", lambda a, s, timestamps=timestamps: fetch_lyrics_lyricsovh(a, s)),
        5: ("ChartLyrics", lambda a, s, timestamps=timestamps: fetch_lyrics_chartlyrics(a, s)),
        6: ("LyricsFreek", lambda a, s, timestamps=timestamps: fetch_lyrics_lyricsfreek(a, s))
    }

    # Default sequences
    default_synced_sequence = [2, 3]  # LRCLIB, YouTube Music
    default_plain_sequence = [1, 4, 5, 6, 2, 3]  # Genius, Lyrics.ovh, ChartLyrics, LyricsFreek, LRCLIB, YouTube Music
    final_fallback_sequence = [2, 3]  # LRCLIB, YouTube Music for plain lyrics

    if pass_param and sequence:
        try:
            # Parse sequence and validate
            sequence = [int(x) for x in sequence.split(",")]
            if not all(1 <= x <= 6 for x in sequence) or len(sequence) > 6 or len(sequence) != len(set(sequence)):
                return {
                    "status": "error",
                    "error": {
                        "message": "Invalid sequence: must be unique numbers between 1 and 6",
                        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                    }
                }
            fetcher_list = [(all_fetchers[num][0], all_fetchers[num][1]) for num in sequence]
            # If sequence length is less than 6, append remaining fetchers in default order
            if len(sequence) < 6:
                if timestamps:
                    remaining = [x for x in default_synced_sequence if x not in sequence]
                    fetcher_list += [(all_fetchers[num][0], all_fetchers[num][1]) for num in remaining]
                else:
                    remaining = [x for x in default_plain_sequence if x not in sequence]
                    fetcher_list += [(all_fetchers[num][0], all_fetchers[num][1]) for num in remaining]
        except ValueError:
            return {
                "status": "error",
                "error": {
                    "message": "Invalid sequence format: must be comma-separated integers",
                    "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                }
            }
    else:
        # Default behavior when pass=false
        if timestamps:
            fetcher_list = [(all_fetchers[num][0], all_fetchers[num][1]) for num in default_synced_sequence]
        else:
            fetcher_list = [(all_fetchers[num][0], all_fetchers[num][1]) for num in default_plain_sequence]

    if timestamps:
        # Step 1: Try specified or default sequence for synced lyrics
        for api_name, fetcher in fetcher_list:
            try:
                result = await maybe_await(fetcher, artist_name, song_title, timestamps=True if api_name in ["YouTube Music", "LRCLIB"] else False)
                if result and result.get("hasTimestamps"):
                    return {
                        "status": "success",
                        "data": result,
                        "attempts": attempts
                    }
                attempts.append({"api": api_name, "status": "no_results" if result else "no_synced_lyrics"})
            except Exception as e:
                logger.error(f"{api_name} error: {str(e)}")
                attempts.append({"api": api_name, "status": "error", "message": str(e)})

        # Step 2: Fall back to plain lyrics in default order if no synced lyrics found
        plain_fetcher_list = [(all_fetchers[num][0], all_fetchers[num][1]) for num in default_plain_sequence[:4]]  # Exclude LRCLIB, YouTube Music
        for api_name, fetcher in plain_fetcher_list:
            try:
                result = await maybe_await(fetcher, artist_name, song_title, timestamps=False)
                if result:
                    return {
                        "status": "success",
                        "data": result,
                        "attempts": attempts
                    }
                attempts.append({"api": api_name, "status": "no_results"})
            except Exception as e:
                logger.error(f"{api_name} error: {str(e)}")
                attempts.append({"api": api_name, "status": "error", "message": str(e)})

    # Step 3: If timestamps=False or no synced lyrics found, try plain lyrics
    for api_name, fetcher in fetcher_list:
        try:
            result = await maybe_await(fetcher, artist_name, song_title, timestamps=False)
            if result:
                return {
                    "status": "success",
                    "data": result,
                    "attempts": attempts
                }
            attempts.append({"api": api_name, "status": "no_results"})
        except Exception as e:
            logger.error(f"{api_name} error: {str(e)}")
            attempts.append({"api": api_name, "status": "error", "message": str(e)})

    # Step 4: Final fallback to LRCLIB and YouTube Music for plain lyrics
    final_fallback_fetchers = [
        ("LRCLIB", lambda a, s, timestamps=False: fetch_lyrics_lrclib(a, s, timestamps)),
        ("YouTube Music", lambda a, s, timestamps=False: fetch_lyrics_youtube(a, s, timestamps))
    ]
    for api_name, fetcher in final_fallback_fetchers:
        try:
            result = await maybe_await(fetcher, artist_name, song_title, timestamps=False)
            if result:
                return {
                    "status": "success",
                    "data": result,
                    "attempts": attempts
                }
            attempts.append({"api": api_name, "status": "no_results"})
        except Exception as e:
            logger.error(f"{api_name} error: {str(e)}")
            attempts.append({"api": api_name, "status": "error", "message": str(e)})

    # If all attempts fail
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
        "api": "Lyrica",
        "version": "1.2-o1-final",
        "status": "active",
        "endpoints": {
            "lyrics": "/lyrics/?artist=ARTIST&song=SONG&timestamp=true&pass=false&sequence=1,2,3,4,5,6"
        },
        "supported_sources": {
            "1": "Genius",
            "2": "LRCLIB",
            "3": "YouTube Music",
            "4": "Lyrics.ovh",
            "5": "ChartLyrics",
            "6": "LyricsFreek"
        },
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    })

@app.route('/lyrics/', methods=['GET'])
async def get_lyrics():
    artist = request.args.get('artist', '').strip()
    song = request.args.get('song', '').strip()

    # Accept both 'timestamp' and 'timestamps' as true if either is set to 'true'
    timestamps = (
        request.args.get('timestamps', 'false').lower() == 'true'
        or request.args.get('timestamp', 'false').lower() == 'true'
    )
    pass_param = request.args.get('pass', 'false').lower() == 'true'
    sequence = request.args.get('sequence', None)
    
    if not artist or not song:
        return jsonify({
            "status": "error",
            "error": {
                "message": "Artist and song name are required",
                "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            }
        }), 400

    if pass_param and not sequence:
        return jsonify({
            "status": "error",
            "error": {
                "message": "Sequence parameter is required when pass=true",
                "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            }
        }), 400

    logger.info(f"Lyrics request received for {artist} - {song}")
    result = await fetch_lyrics(artist, song, timestamps, pass_param, sequence)
    return jsonify(result)

@app.route('/favicon.ico')
def favicon():
    return '', 204

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=9999)
