"""Static information about the Lyrica v1.5.0 API surface."""

from __future__ import annotations

from . import TARGET_API_VERSION, __version__

SERVER_NAME = "lyrica"
SERVER_TITLE = "Lyrica v1.5.0"

INSTRUCTIONS = """\
Lyrica is a multi-provider lyrics aggregation API (stable v1.5.0).

Use these tools to fetch plain or synchronized lyrics, song metadata, trending
charts, autocomplete suggestions, query analytics, and JioSaavn search/stream
links. Lyrics tools can return line-level timestamps, word-level karaoke
timing, syllable-level timing, AI translation, and romanization when the Lyrica
server has the required provider tokens / GROQ_API_KEY configured.

Rules of thumb:
- Prefer `lyrica_get_lyrics` for lyrics and pass `timestamps=true` for synced
  lyrics; add `word=true` for karaoke timing or `syllabus=true` for syllables.
- Use `lyrica_search_suggestions` first when you are unsure of the exact
  artist/title spelling.
- Use `lyrica_get_metadata` when only album/artwork/release information is
  needed.
- The tools proxy a Lyrica v1.5.0 REST API. Failures from Lyrica are reported
  as tool errors with the upstream HTTP status.
"""

PROVIDERS = [
    {
        "id": 1,
        "name": "genius",
        "sync": "plain",
        "auth": "GENIUS_TOKEN optional (public web fallback)",
    },
    {
        "id": 2,
        "name": "lrclib",
        "sync": "line",
        "auth": "none",
    },
    {
        "id": 3,
        "name": "youtube",
        "sync": "line",
        "auth": "temporarily disabled in v1.5.0 builds",
    },
    {
        "id": 4,
        "name": "netease",
        "sync": "line",
        "auth": "none",
    },
    {
        "id": 5,
        "name": "megalobiz",
        "sync": "line",
        "auth": "none",
    },
    {
        "id": 6,
        "name": "musixmatch",
        "sync": "line",
        "auth": "MUSIXMATCH_TOKEN required to load",
    },
    {
        "id": 7,
        "name": "lrcmux",
        "sync": "line, word",
        "auth": "none",
    },
    {
        "id": 8,
        "name": "apple_music",
        "sync": "line, word, syllable",
        "auth": "APPLE_MUSIC_DEVELOPER_TOKEN required to load",
    },
]

DEFAULT_SEQUENCE = ["lrclib", "lrcmux", "genius", "youtube", "netease", "megalobiz", "musixmatch", "apple_music"]

TRENDING_COUNTRIES = ["US", "GB", "IN", "BR", "JP", "DE", "FR", "CA", "AU", "MX"]

TOOL_NAMES = [
    "lyrica_get_lyrics",
    "lyrica_get_metadata",
    "lyrica_search_suggestions",
    "lyrica_get_trending",
    "lyrica_get_top_queries",
    "lyrica_get_trending_by_country",
    "lyrica_compare_trending_vs_queries",
    "lyrica_get_trending_intersection",
    "lyrica_search_jiosaavn",
    "lyrica_get_jiosaavn_stream",
    "lyrica_get_health",
    "lyrica_get_cache_stats",
]

ENDPOINTS = {
    "lyrics": "GET /lyrics/",
    "metadata": "GET /metadata/",
    "suggestions": "GET /suggestion",
    "trending": "GET /trending/",
    "top_queries": "GET /analytics/top-queries/",
    "trending_by_country": "GET /analytics/trending-by-country/",
    "trending_vs_queries": "GET /analytics/trending-vs-queries/",
    "trending_intersection": "GET /analytics/trending-intersection/",
    "jiosaavn_search": "GET /api/jiosaavn/search",
    "jiosaavn_play": "GET /api/jiosaavn/play",
    "health": "GET /health",
    "readiness": "GET /health/ready",
    "cache_stats": "GET /cache/stats",
}


def api_info(base_url: str) -> dict:
    """Return machine-readable server/API metadata for the MCP resource."""
    return {
        "mcp_server": {
            "name": SERVER_NAME,
            "title": SERVER_TITLE,
            "version": __version__,
        },
        "target_api": {
            "name": "Lyrica",
            "version": TARGET_API_VERSION,
            "release_channel": "stable",
            "base_url": base_url,
        },
        "endpoints": ENDPOINTS,
        "default_provider_sequence": DEFAULT_SEQUENCE,
        "trending_countries": TRENDING_COUNTRIES,
        "tools": TOOL_NAMES,
    }
