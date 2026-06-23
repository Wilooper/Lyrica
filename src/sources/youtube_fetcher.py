"""
src/sources/youtube_fetcher.py

Multi-layer YouTube lyrics extractor.

Layer 1 — ytmusicapi.get_lyrics()
  Fastest path: uses YouTube Music's official lyrics API.
  Works for most songs on the YT Music catalog.

Layer 2 — youtube-transcript-api
  Fetches auto-generated captions / subtitles by video ID.
  Works for music videos, fan-uploaded tracks, and any video with captions.
  Produces timed_lyrics from caption timestamps.

Layer 3 — yt-dlp subtitle extraction
  Most robust: downloads VTT/SRT subtitles via yt-dlp.
  Slowest but catches everything Layer 1 & 2 miss.

Each layer is tried in order; first success wins.
All layers run blocking code in a thread pool to stay async-safe.
"""

import asyncio
import re
import tempfile
import os
from datetime import datetime, timezone
from src.logger import get_logger
from .base_fetcher import BaseFetcher, build_result

logger = get_logger("youtube_fetcher")

# Regex to strip VTT timing/formatting tags for plain-text conversion
_VTT_TAG_RE   = re.compile(r"<[^>]+>")
_VTT_TS_RE    = re.compile(
    r"(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})"
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _vtt_ts_to_ms(ts: str) -> int:
    """Convert HH:MM:SS.mmm to milliseconds."""
    h, m, s_ms = ts.split(":")
    s, ms = s_ms.split(".")
    return (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(ms)


def _parse_vtt(vtt_text: str) -> tuple[str, list]:
    """
    Parse WebVTT subtitle text.
    Returns (plain_text, timed_lyrics_list).
    timed_lyrics entries: {text, start_time, end_time, id}
    """
    timed = []
    lines = vtt_text.splitlines()
    i = 0
    seen_texts = set()   # de-duplicate duplicate cue entries

    while i < len(lines):
        line = lines[i].strip()
        m = _VTT_TS_RE.match(line)
        if m:
            start_ms = _vtt_ts_to_ms(m.group(1))
            end_ms   = _vtt_ts_to_ms(m.group(2))
            i += 1
            text_lines = []
            while i < len(lines) and lines[i].strip():
                text_lines.append(lines[i].strip())
                i += 1
            raw_text = " ".join(text_lines)
            clean = _VTT_TAG_RE.sub("", raw_text).strip()
            if clean and clean not in seen_texts:
                seen_texts.add(clean)
                timed.append({
                    "text":       clean,
                    "start_time": start_ms,
                    "end_time":   end_ms,
                    "id":         f"yt_{len(timed)}",
                })
        i += 1

    plain = "\n".join(e["text"] for e in timed)
    return plain, timed


def _parse_transcript(data: list) -> tuple[str, list]:
    """
    Convert youtube-transcript-api result list into (plain, timed).
    Each entry: {text, start, duration}
    """
    timed = []
    for i, seg in enumerate(data):
        text = _VTT_TAG_RE.sub("", seg.get("text", "")).strip()
        if not text:
            continue
        start_ms = int(seg.get("start", 0) * 1000)
        dur_ms   = int(seg.get("duration", 3) * 1000)
        timed.append({
            "text":       text,
            "start_time": start_ms,
            "end_time":   start_ms + dur_ms,
            "id":         f"yt_{i}",
        })
    plain = "\n".join(e["text"] for e in timed)
    return plain, timed


# ─────────────────────────────────────────────────────────────────────────────
# Fetcher
# ─────────────────────────────────────────────────────────────────────────────

class YoutubeFetcher(BaseFetcher):
    source_name = "youtube_music"

    # Singleton YTMusic instance — creating it is expensive (network call).
    _ytmusic = None

    @classmethod
    def _get_ytmusic(cls):
        if cls._ytmusic is None:
            try:
                from ytmusicapi import YTMusic
                cls._ytmusic = YTMusic()
                logger.info("YTMusic instance created")
            except Exception as e:
                logger.error(f"Failed to create YTMusic instance: {e}")
        return cls._ytmusic

    # ------------------------------------------------------------------ #
    # Internal: run blocking calls in thread pool
    # ------------------------------------------------------------------ #
    async def _run(self, fn, *args, timeout: float = 12.0):
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, fn, *args),
            timeout=timeout,
        )

    # ------------------------------------------------------------------ #
    # Layer 1 — ytmusicapi.get_lyrics()
    # ------------------------------------------------------------------ #
    async def _layer1_ytmusic(self, artist: str, song: str, timestamps: bool):
        """Original ytmusicapi path. Returns build_result dict or None."""
        ytmusic = self._get_ytmusic()
        if not ytmusic:
            return None

        try:
            results = await self._run(
                lambda: ytmusic.search(
                    query=f"{song} {artist}", filter="songs", limit=3
                )
            )
            if not results:
                return None

            artist_lower = artist.lower()
            video_id = None
            for r in results:
                r_artist = " ".join(
                    a.get("name", "") for a in (r.get("artists") or [])
                ).lower()
                if artist_lower in r_artist:
                    video_id = r.get("videoId")
                    break
            if not video_id:
                video_id = results[0].get("videoId")
            if not video_id:
                return None

            watch = await self._run(lambda: ytmusic.get_watch_playlist(videoId=video_id))
            browse_id = watch.get("lyrics") if watch else None
            if not browse_id:
                return None

            lyrics_data = await self._run(lambda: ytmusic.get_lyrics(browseId=browse_id))
            if not lyrics_data:
                return None

            raw = lyrics_data.get("lyrics")
            if not raw:
                return None

            if isinstance(raw, str):
                plain_text = raw
                timed = None
            elif isinstance(raw, list):
                plain_text = "\n".join(
                    getattr(line, "text", str(line)) for line in raw
                )
                timed = None
                if timestamps and lyrics_data.get("hasTimestamps"):
                    try:
                        timed = [
                            {
                                "text":       getattr(line, "text", ""),
                                "start_time": getattr(line, "start_time", None),
                                "end_time":   getattr(line, "end_time", None),
                                "id":         getattr(line, "line_id", f"yt_{i}"),
                            }
                            for i, line in enumerate(raw)
                        ]
                    except Exception:
                        timed = None
            else:
                return None

            logger.info(f"[Layer1/ytmusicapi] success for {artist} - {song}")
            return build_result(
                source="youtube_music",
                artist=artist,
                title=song,
                lyrics=plain_text,
                timed_lyrics=timed,
                has_timestamps=bool(timed),
            )

        except asyncio.TimeoutError:
            logger.warning(f"[Layer1/ytmusicapi] timeout for {artist} - {song}")
            return None
        except Exception as e:
            logger.warning(f"[Layer1/ytmusicapi] error: {e}")
            return None

    # ------------------------------------------------------------------ #
    # Layer 2 — youtube-transcript-api
    # ------------------------------------------------------------------ #
    async def _layer2_transcript_api(self, artist: str, song: str, timestamps: bool):
        """
        Search YT Music for the video ID, then fetch captions via
        youtube-transcript-api. Produces timed lyrics from caption timestamps.
        """
        try:
            from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
        except ImportError:
            logger.warning("youtube-transcript-api not installed — Layer 2 skipped")
            return None

        ytmusic = self._get_ytmusic()
        if not ytmusic:
            return None

        try:
            # Search to get a video ID
            results = await self._run(
                lambda: ytmusic.search(
                    query=f"{song} {artist}", filter="songs", limit=5
                )
            )
            if not results:
                return None

            # Try each candidate video ID until one has a transcript
            artist_lower = artist.lower()
            video_ids = []
            for r in results:
                r_artist = " ".join(
                    a.get("name", "") for a in (r.get("artists") or [])
                ).lower()
                vid = r.get("videoId")
                if vid:
                    # Prefer artist-matching results first
                    if artist_lower in r_artist:
                        video_ids.insert(0, vid)
                    else:
                        video_ids.append(vid)

            if not video_ids:
                return None

            # Language preference: English first, then any
            lang_prefs = ["en", "en-US", "en-GB"]

            for vid in video_ids[:3]:
                try:
                    def _fetch_transcript(video_id=vid):
                        api = YouTubeTranscriptApi()
                        # Try preferred languages, fall back to auto-generated
                        try:
                            transcript_list = api.list(video_id)
                            # Try manually created first
                            try:
                                t = transcript_list.find_manually_created_transcript(lang_prefs)
                            except Exception:
                                t = transcript_list.find_generated_transcript(lang_prefs)
                            return t.fetch()
                        except Exception:
                            # Last resort: fetch whatever is available
                            return api.fetch(video_id, languages=lang_prefs + ["a.en"])

                    data = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(None, _fetch_transcript),
                        timeout=12.0,
                    )

                    if not data:
                        continue

                    # Convert FetchedTranscript / list to plain list of dicts
                    entries = list(data)   # FetchedTranscript is iterable
                    if not entries:
                        continue

                    plain, timed = _parse_transcript(entries)
                    if not plain:
                        continue

                    use_timed = timed if timestamps else None
                    logger.info(
                        f"[Layer2/transcript-api] success for {artist} - {song} "
                        f"(videoId={vid}, {len(timed)} segments)"
                    )
                    return build_result(
                        source="youtube_transcript",
                        artist=artist,
                        title=song,
                        lyrics=plain,
                        timed_lyrics=use_timed,
                        has_timestamps=bool(use_timed),
                    )

                except (NoTranscriptFound, TranscriptsDisabled):
                    logger.debug(f"[Layer2] no transcript for videoId={vid}")
                    continue
                except asyncio.TimeoutError:
                    logger.warning(f"[Layer2] timeout for videoId={vid}")
                    continue
                except Exception as e:
                    logger.debug(f"[Layer2] error for videoId={vid}: {e}")
                    continue

            return None

        except asyncio.TimeoutError:
            logger.warning(f"[Layer2/transcript-api] search timeout for {artist} - {song}")
            return None
        except Exception as e:
            logger.warning(f"[Layer2/transcript-api] error: {e}")
            return None

    # ------------------------------------------------------------------ #
    # Layer 3 — yt-dlp subtitle extraction
    # ------------------------------------------------------------------ #
    async def _layer3_ytdlp(self, artist: str, song: str, timestamps: bool):
        """
        Use yt-dlp to search YouTube and download auto-subtitles (VTT).
        Slowest but most robust fallback.
        """
        try:
            import yt_dlp
        except ImportError:
            logger.warning("yt-dlp not installed — Layer 3 skipped")
            return None

        query = f"{song} {artist} official audio"

        with tempfile.TemporaryDirectory() as tmpdir:
            vtt_path = None
            try:
                ydl_opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "writeautomaticsub": True,
                    "writesubtitles": True,
                    "subtitleslangs": ["en", "en-US"],
                    "subtitlesformat": "vtt",
                    "skip_download": True,
                    "outtmpl": os.path.join(tmpdir, "%(id)s.%(ext)s"),
                    "default_search": "ytsearch1",
                    "noplaylist": True,
                    "socket_timeout": 10,
                }

                def _dl():
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(f"ytsearch1:{query}", download=True)
                        if info and "entries" in info:
                            info = info["entries"][0]
                        return info

                info = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, _dl),
                    timeout=20.0,
                )

                if not info:
                    return None

                # Find downloaded VTT file
                vid_id = info.get("id", "")
                for fname in os.listdir(tmpdir):
                    if fname.startswith(vid_id) and fname.endswith(".vtt"):
                        vtt_path = os.path.join(tmpdir, fname)
                        break

                if not vtt_path or not os.path.exists(vtt_path):
                    logger.debug(f"[Layer3/yt-dlp] no VTT file downloaded for '{query}'")
                    return None

                with open(vtt_path, encoding="utf-8", errors="replace") as f:
                    vtt_text = f.read()

                plain, timed = _parse_vtt(vtt_text)
                if not plain:
                    return None

                use_timed = timed if timestamps else None
                logger.info(
                    f"[Layer3/yt-dlp] success for {artist} - {song} "
                    f"({len(timed)} subtitle segments)"
                )
                return build_result(
                    source="youtube_subtitles",
                    artist=artist,
                    title=song,
                    lyrics=plain,
                    timed_lyrics=use_timed,
                    has_timestamps=bool(use_timed),
                )

            except asyncio.TimeoutError:
                logger.warning(f"[Layer3/yt-dlp] timeout for {artist} - {song}")
                return None
            except Exception as e:
                logger.warning(f"[Layer3/yt-dlp] error: {e}")
                return None

    # ------------------------------------------------------------------ #
    # Main fetch — try all layers in order
    # ------------------------------------------------------------------ #
    async def fetch(self, artist: str, song: str, timestamps: bool = False):
        logger.info(f"YouTube fetcher: '{artist} - {song}' (timestamps={timestamps})")

        # Layer 1: ytmusicapi (fastest)
        result = await self._layer1_ytmusic(artist, song, timestamps)
        if result:
            return result

        # Layer 2: youtube-transcript-api (captions)
        logger.info(f"[Layer1] failed, trying Layer2 (transcript-api)...")
        result = await self._layer2_transcript_api(artist, song, timestamps)
        if result:
            return result

        # Layer 3: yt-dlp subtitles (slowest, most robust)
        logger.info(f"[Layer2] failed, trying Layer3 (yt-dlp subtitles)...")
        result = await self._layer3_ytdlp(artist, song, timestamps)
        if result:
            return result

        logger.warning(f"All YouTube layers failed for '{artist} - {song}'")
        return None
