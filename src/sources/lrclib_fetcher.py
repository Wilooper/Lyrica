import re
from datetime import datetime, timezone
import requests
from src.config import LRCLIB_API_URL
from src.logger import get_logger
from .base_fetcher import BaseFetcher

logger = get_logger("lrclib_fetcher")

class LRCLIBFetcher(BaseFetcher):
    def fetch(self, artist: str, song: str, timestamps: bool=True):
        try:
            logger.info(f"Attempting LRCLIB API for {artist} - {song}")
            search_url = "https://lrclib.net/api/search"
            params = {"track_name": song, "artist_name": artist}
            search_resp = requests.get(search_url, params=params, timeout=10)
            if search_resp.status_code != 200:
                return None
            results = search_resp.json()
            if not results:
                return None
            track = results[0]
            get_params = {
                "track_name": track.get("trackName"),
                "artist_name": track.get("artistName"),
                "album_name": track.get("albumName"),
                "duration": track.get("duration")
            }
            get_resp = requests.get(LRCLIB_API_URL, params=get_params, timeout=10)
            if get_resp.status_code != 200:
                return None
            data = get_resp.json()
            lyrics = data.get("syncedLyrics") if timestamps else data.get("plainLyrics")
            if not lyrics:
                return None
            result = {
                "source": "lrclib",
                "artist": data.get("artistName"),
                "title": data.get("trackName"),
                "album": data.get("albumName"),
                "duration": data.get("duration"),
                "instrumental": data.get("instrumental", False),
                "lyrics": lyrics,
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            }
            # parse timed lyrics to timed_lyrics list if timestamps requested
            if timestamps and data.get("syncedLyrics"):
                timed_lyrics = []
                lines = data["syncedLyrics"].split("\n")
                for i, line in enumerate(lines):
                    match = re.match(r"\[(\d{2}:\d{2}\.?\.?\d{2})\](.*)", line)
                    if match:
                        time_str, text = match.groups()
                        time_str = time_str.replace("..", ".")
                        try:
                            minutes, seconds = map(float, time_str.split(":"))
                            start_time = int((minutes * 60 + seconds) * 1000)
                            end_time = None
                            if i < len(lines) - 1:
                                next_match = re.match(r"\[(\d{2}:\d{2}\.?\.?\d{2})\](.*)", lines[i + 1])
                                if next_match:
                                    next_time_str = next_match.group(1).replace("..", ".")
                                    next_minutes, next_seconds = map(float, next_time_str.split(":"))
                                    end_time = int((next_minutes * 60 + next_seconds) * 1000)
                                else:
                                    end_time = start_time + 4000
                            else:
                                end_time = start_time + 4000 if not data.get("duration") else int(data["duration"] * 1000)
                            if text.strip():
                                timed_lyrics.append({"text": text.strip(), "start_time": start_time, "end_time": end_time, "id": f"lrc_{i}"})
                        except ValueError:
                            continue
                if timed_lyrics:
                    result["timed_lyrics"] = timed_lyrics
                    result["hasTimestamps"] = True
            return result
        except Exception as e:
            logger.error(f"LRCLIB API error: {e}")
            return None
