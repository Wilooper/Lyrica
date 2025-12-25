import requests
from datetime import datetime, timezone
from src.logger import get_logger
from .base_fetcher import BaseFetcher

logger = get_logger("simpmusic_fetcher")

API_BASE = "https://api-lyrics.simpmusic.org/v1"

class SimpMusicFetcher(BaseFetcher):
    def search_song(self, title: str, artist: str = None):
        try:
            params = {"q": title}
            resp = requests.get(f"{API_BASE}/search", params=params, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"SimpMusic search error: {e}")
            return None

    def get_lyrics(self, video_id: str):
        try:
            resp = requests.get(f"{API_BASE}/{video_id}", timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"SimpMusic lyrics fetch error: {e}")
            return None

    def fetch(self, artist: str, song: str, timestamps: bool=False):
        logger.info(f"Attempting SimpMusic API for {artist} - {song}")
        search_data = self.search_song(song, artist)
        if not search_data:
            return None
        results = search_data.get("data") if isinstance(search_data, dict) else search_data
        if not results:
            return None
        first = results[0]
        video_id = first.get("videoId") or first.get("id")
        if not video_id:
            return None
        lyric_data = self.get_lyrics(video_id)
        if not lyric_data:
            return None
        d = lyric_data.get("data")
        if isinstance(d, list) and len(d) > 0:
            d = d[0]
        if not isinstance(d, dict):
            return None
        result = {
            "source": "simpmusic",
            "artist": first.get("artistName") or artist,
            "title": first.get("title") or song,
            "lyrics": d.get("plainLyrics") or d.get("lyrics") or None,
            "timestamped": d.get("syncedLyrics") or d.get("lrc") or None,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        }
        # For compatibility: if timestamps requested and synced is present expose timed_lyrics
        if timestamps and result.get("timestamped"):
            lines = result["timestamped"].split("\n")
            timed = []
            for i, line in enumerate(lines):
                # simple parse: [MM:SS.xx]text
                import re
                m = re.match(r"\[(\d{2}:\d{2}\.?\d{0,2})\](.*)", line)
                if m:
                    tstr, text = m.groups()
                    tstr = tstr.replace("..", ".")
                    try:
                        mm, ss = tstr.split(":")
                        total = int(mm) * 60 * 1000 + int(float(ss) * 1000)
                        timed.append({"text": text.strip(), "start_time": total, "end_time": None, "id": f"sim_{i}"})
                    except Exception:
                        continue
            if timed:
                result["timed_lyrics"] = timed
                result["hasTimestamps"] = True
        return result
