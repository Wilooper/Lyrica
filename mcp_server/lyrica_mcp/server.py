"""MCP server definition for the stable Lyrica v1.5.0 API."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Any, AsyncIterator

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from . import TARGET_API_VERSION, __version__
from .client import LyricaAPIError, LyricaClient
from .config import Settings
from .constants import (
    DEFAULT_SEQUENCE,
    INSTRUCTIONS,
    PROVIDERS,
    SERVER_NAME,
    SERVER_TITLE,
    api_info,
)
from .operations import LyricaOperations, ToolInputError

logger = logging.getLogger(__name__)

_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    idempotentHint=True,
    openWorldHint=True,
)

Artist = Annotated[str, Field(min_length=1, max_length=200, description="Artist or band name.")]
Song = Annotated[str, Field(min_length=1, max_length=200, description="Song or track title.")]
Limit = Annotated[int, Field(ge=1, le=100, description="Maximum number of results (1-100).")]
CountryCode = Annotated[
    str,
    Field(
        pattern=r"^[A-Za-z]{2}$",
        description="ISO 3166-1 alpha-2 country code, for example US, GB, or IN.",
    ),
]


@dataclass(slots=True)
class AppContext:
    """Lifespan state shared by all tool calls."""

    client: LyricaClient


def _ops(ctx: Context) -> LyricaOperations:
    lifespan = ctx.request_context.lifespan_context
    if not isinstance(lifespan, AppContext):
        raise ToolError("Lyrica MCP server is not initialized")
    return LyricaOperations(lifespan.client)


async def _call(coro: Any) -> dict[str, Any]:
    """Translate upstream/validation failures into MCP tool errors."""
    try:
        return await coro
    except (LyricaAPIError, ToolInputError) as exc:
        raise ToolError(str(exc)) from exc


def create_server(
    settings: Settings,
    *,
    client_factory: Callable[[], LyricaClient] | None = None,
) -> MCPServer:
    """Build a configured MCP server instance.

    ``client_factory`` is primarily for tests; production callers should leave
    it unset so a single shared ``LyricaClient`` is created in the lifespan.
    """
    make_client = client_factory or (lambda: LyricaClient(settings))

    @asynccontextmanager
    async def lifespan(_server: MCPServer) -> AsyncIterator[AppContext]:
        client = make_client()
        logger.info("Lyrica MCP server targeting %s (API v%s)", settings.base_url, TARGET_API_VERSION)
        try:
            yield AppContext(client=client)
        finally:
            await client.close()

    mcp = MCPServer(
        name=SERVER_NAME,
        title=SERVER_TITLE,
        description=(
            "Lyrics, synchronized timing, metadata, trending charts, and music "
            "discovery from the stable Lyrica v1.5.0 API."
        ),
        instructions=INSTRUCTIONS,
        version=__version__,
        lifespan=lifespan,
        log_level=settings.log_level,
    )

    # ── Lyrics & metadata ────────────────────────────────────────────────

    @mcp.tool(title="Get lyrics", annotations=_READ_ONLY)
    async def lyrica_get_lyrics(
        ctx: Context,
        artist: Artist,
        song: Song,
        timestamps: Annotated[
            bool,
            Field(description="Return synchronized lyrics with start/end millisecond timestamps."),
        ] = False,
        word: Annotated[
            bool,
            Field(description="Return word-level karaoke timing (implies timestamps=true)."),
        ] = False,
        syllabus: Annotated[
            bool,
            Field(
                description=(
                    "Return syllable-level timing via Apple Music (implies timestamps=true; "
                    "requires APPLE_MUSIC_DEVELOPER_TOKEN on the Lyrica server)."
                )
            ),
        ] = False,
        translate: Annotated[
            bool,
            Field(description="Translate lyrics via Groq (requires GROQ_API_KEY on the Lyrica server)."),
        ] = False,
        romanize: Annotated[
            bool,
            Field(description="Romanize/transliterate lyrics via Groq (requires GROQ_API_KEY)."),
        ] = False,
        language: Annotated[
            str,
            Field(max_length=40, description="Target language code for translate/romanize, e.g. en, es, hi."),
        ] = "en",
        mood: Annotated[
            bool,
            Field(description="Add sentiment, polarity, subjectivity, and word-frequency analysis."),
        ] = False,
        metadata: Annotated[
            bool,
            Field(description="Enrich the result with album, artwork, genre, and release metadata."),
        ] = False,
        sequence: Annotated[
            str | None,
            Field(
                max_length=500,
                description=(
                    "Optional comma-separated provider IDs or names, e.g. '2,7' or 'lrclib,lrcmux'. "
                    "Omit to use the server's default fallback sequence."
                ),
            ),
        ] = None,
        fast: Annotated[
            bool,
            Field(description="Query providers in parallel and return the first verified match."),
        ] = False,
        pass_through: Annotated[
            bool,
            Field(
                description=(
                    "Strictly use only the providers in sequence without fallback. "
                    "Requires sequence to be set."
                )
            ),
        ] = False,
        country: CountryCode = "US",
    ) -> dict[str, Any]:
        """Fetch lyrics for a song.

        Supports plain lyrics, line-level LRC timestamps, word-level karaoke
        timing, syllable timing, mood analysis, metadata enrichment, AI
        translation, and romanization. The response is the raw Lyrica v1
        success/error envelope.
        """
        return await _call(
            _ops(ctx).get_lyrics(
                artist=artist,
                song=song,
                timestamps=timestamps,
                word=word,
                syllabus=syllabus,
                translate=translate,
                romanize=romanize,
                language=language,
                mood=mood,
                metadata=metadata,
                sequence=sequence,
                fast=fast,
                pass_through=pass_through,
                country=country,
            )
        )

    @mcp.tool(title="Get song metadata", annotations=_READ_ONLY)
    async def lyrica_get_metadata(ctx: Context, artist: Artist, song: Song) -> dict[str, Any]:
        """Fetch album, artwork, release date, genre, duration, and summary without lyrics."""
        return await _call(_ops(ctx).get_metadata(artist=artist, song=song))

    @mcp.tool(title="Search song suggestions", annotations=_READ_ONLY)
    async def lyrica_search_suggestions(
        ctx: Context,
        query: Annotated[str, Field(min_length=1, max_length=200, description="Free-text song or artist query.")],
        limit: Limit = 10,
    ) -> dict[str, Any]:
        """Suggest matching titles and artists (MusicBrainz-backed autocomplete)."""
        return await _call(_ops(ctx).search_suggestions(query=query, limit=limit))

    # ── Trending & analytics ─────────────────────────────────────────────

    @mcp.tool(title="Get trending songs", annotations=_READ_ONLY)
    async def lyrica_get_trending(
        ctx: Context,
        country: CountryCode = "US",
        countries: Annotated[
            str | None,
            Field(
                max_length=64,
                description=(
                    "Optional comma-separated country codes (e.g. 'US,GB,IN'). "
                    "When set, results are grouped per country."
                ),
            ),
        ] = None,
        limit: Limit = 20,
    ) -> dict[str, Any]:
        """Get Apple Music RSS trending songs for one country or several countries.

        Lyrica supports these trending country codes: US, GB, IN, BR, JP, DE,
        FR, CA, AU, and MX.
        """
        return await _call(_ops(ctx).get_trending(country=country, countries=countries, limit=limit))

    @mcp.tool(title="Get top lyric queries", annotations=_READ_ONLY)
    async def lyrica_get_top_queries(
        ctx: Context,
        limit: Limit = 20,
        country: Annotated[
            str | None,
            Field(
                pattern=r"^[A-Za-z]{2}$",
                description="Optional country code to filter queries; omit for global scope.",
            ),
        ] = None,
        days: Annotated[
            int | None,
            Field(ge=1, le=3650, description="Optional lookback window in days; omit for all time."),
        ] = None,
    ) -> dict[str, Any]:
        """Get the most frequently requested lyric search queries."""
        return await _call(_ops(ctx).get_top_queries(limit=limit, country=country, days=days))

    @mcp.tool(title="Get top queries by country", annotations=_READ_ONLY)
    async def lyrica_get_trending_by_country(ctx: Context, limit: Limit = 10) -> dict[str, Any]:
        """Get the top lyric search queries broken down by country."""
        return await _call(_ops(ctx).get_trending_by_country(limit=limit))

    @mcp.tool(title="Compare trending vs queries", annotations=_READ_ONLY)
    async def lyrica_compare_trending_vs_queries(
        ctx: Context,
        country: CountryCode = "US",
        limit: Limit = 10,
    ) -> dict[str, Any]:
        """Cross-analyze Apple Music trending charts against user lyric search traffic."""
        return await _call(_ops(ctx).compare_trending_vs_queries(country=country, limit=limit))

    @mcp.tool(title="Get trending/query intersection", annotations=_READ_ONLY)
    async def lyrica_get_trending_intersection(
        ctx: Context,
        country: CountryCode = "US",
        limit: Limit = 10,
    ) -> dict[str, Any]:
        """Find songs that appear in both the trending chart and user search queries."""
        return await _call(_ops(ctx).get_trending_intersection(country=country, limit=limit))

    # ── JioSaavn ─────────────────────────────────────────────────────────

    @mcp.tool(title="Search JioSaavn", annotations=_READ_ONLY)
    async def lyrica_search_jiosaavn(
        ctx: Context,
        query: Annotated[str, Field(min_length=1, max_length=200, description="Song or artist to search for.")],
    ) -> dict[str, Any]:
        """Search JioSaavn for tracks and their song links."""
        return await _call(_ops(ctx).search_jiosaavn(query=query))

    @mcp.tool(title="Get JioSaavn stream", annotations=_READ_ONLY)
    async def lyrica_get_jiosaavn_stream(
        ctx: Context,
        song_link: Annotated[
            str,
            Field(
                min_length=1,
                max_length=2048,
                description="A JioSaavn song link or token returned by lyrica_search_jiosaavn.",
            ),
        ],
    ) -> dict[str, Any]:
        """Resolve a JioSaavn song link to direct playable audio stream URLs."""
        return await _call(_ops(ctx).get_jiosaavn_stream(song_link=song_link))

    # ── System ───────────────────────────────────────────────────────────

    @mcp.tool(title="Check Lyrica health", annotations=_READ_ONLY)
    async def lyrica_get_health(
        ctx: Context,
        ready: Annotated[
            bool,
            Field(description="Also check optional dependencies (currently Redis) via /health/ready."),
        ] = False,
    ) -> dict[str, Any]:
        """Check that the Lyrica v1.5.0 API is reachable and healthy."""
        return await _call(_ops(ctx).get_health(ready=ready))

    @mcp.tool(title="Get cache statistics", annotations=_READ_ONLY)
    async def lyrica_get_cache_stats(ctx: Context) -> dict[str, Any]:
        """Get public L1/L2/L3 cache statistics from the Lyrica API."""
        return await _call(_ops(ctx).get_cache_stats())

    # ── Resources ────────────────────────────────────────────────────────

    @mcp.resource(
        "lyrica://api/info",
        name="api-info",
        title="Lyrica API information",
        description="Target API version, base URL, endpoints, and exposed MCP tools.",
        mime_type="application/json",
    )
    def api_info_resource() -> str:
        return json.dumps(api_info(settings.base_url), indent=2, ensure_ascii=False)

    @mcp.resource(
        "lyrica://providers",
        name="providers",
        title="Lyrica provider registry",
        description="Lyrics providers, sync capabilities, authentication, and default fallback order.",
        mime_type="application/json",
    )
    def providers_resource() -> str:
        return json.dumps(
            {
                "providers": PROVIDERS,
                "default_sequence": DEFAULT_SEQUENCE,
                "notes": (
                    "Token-gated providers are skipped when their token is not configured. "
                    "Word-level requests route only to lrcmux and apple_music."
                ),
            },
            indent=2,
            ensure_ascii=False,
        )

    # ── Prompts ──────────────────────────────────────────────────────────

    @mcp.prompt(
        title="Fetch lyrics",
        description="Ask the model to fetch lyrics at a specific synchronization level.",
    )
    def fetch_lyrics_prompt(artist: str, song: str, sync: str = "line") -> str:
        sync = (sync or "line").lower()
        if sync not in {"plain", "line", "word", "syllable"}:
            sync = "line"
        flags = {
            "plain": "timestamps=false",
            "line": "timestamps=true",
            "word": "timestamps=true, word=true",
            "syllable": "timestamps=true, syllabus=true",
        }[sync]
        return (
            f"Use the `lyrica_get_lyrics` tool with artist={artist!r}, song={song!r}, {flags}. "
            "Return the lyrics and mention the provider and synchronization level."
        )

    @mcp.prompt(
        title="Explore trending music",
        description="Ask the model to inspect trending music and related search queries.",
    )
    def trending_prompt(country: str = "US", limit: str = "10") -> str:
        return (
            f"Use `lyrica_get_trending` for country={country!r} with limit={limit}, then "
            "`lyrica_compare_trending_vs_queries` for the same country. Summarize which "
            "trending tracks users are also searching for."
        )

    return mcp
