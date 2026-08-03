"""
src/sources/youtube_fetcher.py

Multi-layer YouTube lyrics extractor.

Layer 1 — ytmusicapi.get_lyrics()
  Fastest path: uses YouTube Music's official lyrics API.
  Automatically uses authenticated mode if headers_auth.json or cookies.txt
  are found in the project root (or cwd). Falls back to unauthenticated.

Layer 2 — youtube-transcript-api
  Fetches auto-generated captions / subtitles by video ID.
  Works for music videos, fan-uploaded tracks, and any video with captions.
  Produces timed_lyrics from caption timestamps.
  Routed through the Webshare rotating proxy.

Layer 3 — yt-dlp subtitle extraction
  Most robust: downloads VTT/SRT subtitles via yt-dlp.
  Slowest but catches everything Layer 1 & 2 miss.
  Routed through the Webshare rotating proxy; uses cookies.txt if present.

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
# Webshare rotating proxy configuration
# Credentials are read from environment variables — never hardcoded.
#
# Option A (recommended): set a full proxy URL
#   YT_PROXY_URL=http://user:pass@p.webshare.io:80
#
# Option B: set individual components
#   YT_PROXY_USER=your-username-rotate
#   YT_PROXY_PASS=your-password
#   YT_PROXY_HOST=p.webshare.io
#   YT_PROXY_PORT=80  (default)
#
# If neither is set, all YouTube layers run without a proxy.
# ─────────────────────────────────────────────────────────────────────────────
def _build_proxy_url() -> str | None:
    """Build proxy URL from environment variables. Returns None if not configured."""
    # Option A: full URL already set
    full = os.environ.get("YT_PROXY_URL", "").strip()
    if full:
        return full

    # Option B: individual components
    user = os.environ.get("YT_PROXY_USER", "").strip()
    passwd = os.environ.get("YT_PROXY_PASS", "").strip()
    host = os.environ.get("YT_PROXY_HOST", "").strip()
    port = os.environ.get("YT_PROXY_PORT", "80").strip()
    if user and passwd and host:
        return f"http://{user}:{passwd}@{host}:{port}"

    return None

_PROXY_URL: str | None = _build_proxy_url()


# ─────────────────────────────────────────────────────────────────────────────
# Auth-file detection
# Searches for cookies / headers files relative to the project root.
# ─────────────────────────────────────────────────────────────────────────────
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def _find_auth_file() -> tuple[str | None, str | None]:
    """
    Scan for YT Music authentication files.

    Priority order:
      1. YT_HEADERS_PATH env var  — explicit path to headers_auth.json
      2. YT_COOKIES_PATH env var  — explicit path to cookies.txt
      3. headers_auth.json in project root / cwd / script dir
      4. cookies.txt in project root / cwd / script dir

    Returns (file_path, auth_type) where auth_type is 'headers' or 'cookies',
    or (None, None) if no auth file is found.
    """
    # ── 1. Explicit env vars (useful for hosted/containerised deployments) ──
    env_headers = os.environ.get("YT_HEADERS_PATH", "").strip()
    if env_headers and os.path.isfile(env_headers):
        logger.info(f"[YTMusic] Found headers auth file via YT_HEADERS_PATH: {env_headers}")
        return env_headers, "headers"
    elif env_headers:
        logger.warning(f"[YTMusic] YT_HEADERS_PATH set but file not found: {env_headers}")

    env_cookies = os.environ.get("YT_COOKIES_PATH", "").strip()
    if env_cookies and os.path.isfile(env_cookies):
        logger.info(f"[YTMusic] Found cookies file via YT_COOKIES_PATH: {env_cookies}")
        return env_cookies, "cookies"
    elif env_cookies:
        logger.warning(f"[YTMusic] YT_COOKIES_PATH set but file not found: {env_cookies}")

    # ── 2. Filesystem scan (project root, cwd, script dir) ──────────────────
    search_dirs = [
        _PROJECT_ROOT,
        os.getcwd(),
        os.path.dirname(os.path.abspath(__file__)),
    ]

    for d in search_dirs:
        # headers_auth.json takes priority (richer auth)
        p = os.path.join(d, "headers_auth.json")
        if os.path.isfile(p):
            logger.info(f"[YTMusic] Found headers auth file: {p}")
            return p, "headers"

        # cookies.txt second
        p = os.path.join(d, "cookies.txt")
        if os.path.isfile(p):
            logger.info(f"[YTMusic] Found cookies file: {p}")
            return p, "cookies"

    logger.info("[YTMusic] No auth file found — using unauthenticated mode")
    return None, None


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
    _ytmusic_authenticated = False  # tracks whether the instance uses auth
    _auth_checked = False           # only run auth detection once

    @classmethod
    def _get_ytmusic(cls):
        """
        Return (or lazily create) the YTMusic singleton.

        Auth detection runs once at first call:
          - If headers_auth.json exists  → YTMusic(auth=headers_auth.json)  [authenticated]
          - If cookies.txt exists only   → YTMusic()  [unauthenticated; cookies.txt used by yt-dlp Layer 3]
          - Otherwise                    → YTMusic()  [unauthenticated]

        NOTE: ytmusicapi only accepts a browser-headers JSON file (headers_auth.json)
        as its auth argument. Netscape cookies.txt is NOT supported by ytmusicapi —
        it is passed to yt-dlp in Layer 3 for authenticated YouTube downloads.
        """
        if not cls._auth_checked:
            cls._auth_checked = True
            auth_file, auth_type = _find_auth_file()

            try:
                from ytmusicapi import YTMusic

                if auth_file and auth_type == "headers":
                    # headers_auth.json: browser-headers JSON supported by ytmusicapi
                    cls._ytmusic = YTMusic(auth=auth_file)
                    cls._ytmusic_authenticated = True
                    logger.info("[YTMusic] Authenticated via headers_auth.json")
                else:
                    # cookies.txt is NOT usable by ytmusicapi - only by yt-dlp Layer 3
                    if auth_file and auth_type == "cookies":
                        logger.info(
                            "[YTMusic] cookies.txt detected (for yt-dlp Layer 3); "
                            "ytmusicapi running unauthenticated"
                        )
                    else:
                        logger.info("[YTMusic] No auth file - running unauthenticated")
                    cls._ytmusic = YTMusic()
                    cls._ytmusic_authenticated = False

            except Exception as e:
                logger.error(f"[YTMusic] Failed to create authenticated instance: {e}")
                # Fallback: try unauthenticated
                try:
                    from ytmusicapi import YTMusic
                    cls._ytmusic = YTMusic()
                    cls._ytmusic_authenticated = False
                    logger.warning("[YTMusic] Fell back to unauthenticated mode")
                except Exception as e2:
                    logger.error(f"[YTMusic] Unauthenticated fallback also failed: {e2}")

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
        """ytmusicapi path — authenticated if auth file detected, else open. Returns build_result dict or None."""
        ytmusic = self._get_ytmusic()
        if not ytmusic:
            return None

        auth_label = "authenticated" if self._ytmusic_authenticated else "unauthenticated"
        logger.info(f"[Layer1/ytmusicapi] {auth_label} — searching '{artist} - {song}'")

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

            logger.info(f"[Layer1/ytmusicapi] success for {artist} - {song} ({auth_label})")
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
    # Layer 2 — youtube-transcript-api  (proxied via Webshare)
    # ------------------------------------------------------------------ #
    async def _layer2_transcript_api(self, artist: str, song: str, timestamps: bool):
        """
        Search YT Music for the video ID, then fetch captions via
        youtube-transcript-api routed through the Webshare rotating proxy.
        Produces timed lyrics from caption timestamps.
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

            # Build proxy dict for youtube-transcript-api (only if proxy configured)
            proxy_dict = {"http": _PROXY_URL, "https": _PROXY_URL} if _PROXY_URL else None

            for vid in video_ids[:3]:
                try:
                    def _fetch_transcript(video_id=vid):
                        # Pass proxies kwarg when proxy is configured
                        try:
                            api = YouTubeTranscriptApi(proxies=proxy_dict) if proxy_dict else YouTubeTranscriptApi()
                        except TypeError:
                            # Older API versions may not support proxies kwarg
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
                        f"(videoId={vid}, {len(timed)} segments, proxy=webshare-rotate)"
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
    # Layer 3 — yt-dlp subtitle extraction  (proxied via Webshare)
    # ------------------------------------------------------------------ #
    async def _layer3_ytdlp(self, artist: str, song: str, timestamps: bool):
        """
        Use yt-dlp to search YouTube and download auto-subtitles (VTT).
        All requests routed through the Webshare rotating proxy.
        cookies.txt is passed to yt-dlp when available.
        Slowest but most robust fallback.
        """
        try:
            import yt_dlp
        except ImportError:
            logger.warning("yt-dlp not installed — Layer 3 skipped")
            return None

        query = f"{song} {artist} official audio"

        # Detect cookies file for yt-dlp (only .txt files, not headers JSON)
        auth_path, auth_type = _find_auth_file()
        cookies_file: str | None = None
        if auth_path and auth_type == "cookies":
            cookies_file = auth_path

        with tempfile.TemporaryDirectory() as tmpdir:
            vtt_path = None
            try:
                ydl_opts: dict = {
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

                # Only add proxy if configured via environment variable
                if _PROXY_URL:
                    ydl_opts["proxy"] = _PROXY_URL

                if cookies_file:
                    ydl_opts["cookiefile"] = cookies_file
                    logger.info(f"[Layer3/yt-dlp] using cookies from: {cookies_file}")

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
                    f"({len(timed)} subtitle segments, proxy=webshare-rotate)"
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
        auth_label = "authenticated" if self._ytmusic_authenticated else "unauthenticated"
        proxy_label = "proxy=configured" if _PROXY_URL else "proxy=none"
        logger.info(
            f"YouTube fetcher: '{artist} - {song}' "
            f"(timestamps={timestamps}, ytmusic={auth_label}, {proxy_label})"
        )

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
