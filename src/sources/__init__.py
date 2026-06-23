"""
sources/__init__.py

Exposes ALL_FETCHERS: a dict of fetcher name → fetcher instance.

Fetchers are instantiated lazily (at import time here, but each fetcher's
internal clients are lazy too) so a missing optional dependency like
lyricsgenius or ytmusicapi won't crash the whole server — it will just
make that fetcher silently unavailable.

Source status (as of 2026-06-23):
  ACTIVE:
    genius      — requires GENIUS_TOKEN env var
    lrclib      — free, synced + plain, very reliable
    youtube     — 3-layer (ytmusicapi -> transcript-api -> yt-dlp)
    simpmusic   — synced + plain via api-lyrics.simpmusic.org
    netease     — via syncedlyrics; synced LRC, large catalog
    megalobiz   — via syncedlyrics; synced LRC, user-contributed
    musixmatch  — via syncedlyrics; optional MUSIXMATCH_TOKEN env var

  DISABLED (dead as of 2026-06-23 — kept for reference, not loaded):
    lyricsovh   — no results / unreliable
    chartlyrics — XML API dead
    lyricsfreek — DNS failure (domain dead)
"""
from src.logger import get_logger

logger = get_logger("sources")

ALL_FETCHERS: dict = {}

def _try_import(name: str, module: str, cls: str):
    try:
        mod = __import__(module, fromlist=[cls])
        instance = getattr(mod, cls)()
        ALL_FETCHERS[name] = instance
        logger.info(f"Fetcher loaded: {name}")
    except Exception as e:
        logger.warning(f"Fetcher '{name}' unavailable: {e}")

# ── Active fetchers ──────────────────────────────────────────────────────────
_try_import("genius",     "src.sources.genius_fetcher",      "GeniusFetcher")
_try_import("lrclib",     "src.sources.lrclib_fetcher",      "LRCLIBFetcher")
_try_import("youtube",    "src.sources.youtube_fetcher",     "YoutubeFetcher")
_try_import("simpmusic",  "src.sources.simp_music_fetcher",  "SimpMusicFetcher")
_try_import("netease",    "src.sources.netease_fetcher",     "NetEaseFetcher")
_try_import("megalobiz",  "src.sources.megalobiz_fetcher",   "MegalobizFetcher")
_try_import("musixmatch", "src.sources.musixmatch_fetcher",  "MusixmatchFetcher")

# ── Disabled fetchers (dead APIs — do NOT load into ALL_FETCHERS) ────────────
# _try_import("lyricsovh",   "src.sources.lyricsovh_fetcher",   "LyricsOvhFetcher")   # dead
# _try_import("chartlyrics", "src.sources.chartlyrics_fetcher", "ChartLyricsFetcher") # dead
# _try_import("lyricsfreek", "src.sources.lyricsfreek_fetcher", "LyricsFreekFetcher") # DNS dead

logger.info(f"Active fetchers: {list(ALL_FETCHERS.keys())}")
