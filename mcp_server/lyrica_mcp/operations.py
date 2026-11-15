"""Validation and orchestration for the tools exposed over MCP."""

from __future__ import annotations

from .client import JSON, LyricaClient
from .constants import TRENDING_COUNTRIES


class ToolInputError(ValueError):
    """Raised when tool arguments are valid JSON but not usable by Lyrica."""


def _text(value: str, field: str, *, max_length: int = 200) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ToolInputError(f"{field} must not be empty")
    if len(cleaned) > max_length:
        raise ToolInputError(f"{field} must be at most {max_length} characters")
    return cleaned


def _limit(value: int, *, maximum: int = 100) -> int:
    if not 1 <= value <= maximum:
        raise ToolInputError(f"limit must be between 1 and {maximum}")
    return value


def _country_code(value: str) -> str:
    code = (value or "").strip().upper()
    if len(code) != 2 or not code.isalpha():
        raise ToolInputError(f"{value!r} is not a two-letter ISO country code")
    return code


def _trending_country(value: str) -> str:
    code = _country_code(value)
    if code not in TRENDING_COUNTRIES:
        raise ToolInputError(
            f"Unsupported trending country code {value!r}. Supported codes: {', '.join(TRENDING_COUNTRIES)}"
        )
    return code


class LyricaOperations:
    """Tool implementations, separated from MCP registration for testability."""

    def __init__(self, client: LyricaClient) -> None:
        self.client = client

    async def get_lyrics(
        self,
        *,
        artist: str,
        song: str,
        timestamps: bool = False,
        word: bool = False,
        syllabus: bool = False,
        translate: bool = False,
        romanize: bool = False,
        language: str = "en",
        mood: bool = False,
        metadata: bool = False,
        sequence: str | None = None,
        fast: bool = False,
        pass_through: bool = False,
        country: str = "US",
    ) -> JSON:
        artist = _text(artist, "artist")
        song = _text(song, "song")
        country = _country_code(country)

        if sequence is not None:
            sequence = sequence.strip() or None
            if sequence and len(sequence) > 500:
                raise ToolInputError("sequence must be at most 500 characters")
        if pass_through and not sequence:
            raise ToolInputError("pass_through=true requires a non-empty sequence")

        # The v1 API only produces word/syllable timing for timed requests.
        if word or syllabus:
            timestamps = True

        language = (language or "en").strip().lower() or "en"
        if len(language) > 40:
            raise ToolInputError("language must be at most 40 characters")

        return await self.client.get_lyrics(
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

    async def get_metadata(self, *, artist: str, song: str) -> JSON:
        return await self.client.get_metadata(
            artist=_text(artist, "artist"),
            song=_text(song, "song"),
        )

    async def search_suggestions(self, *, query: str, limit: int = 10) -> JSON:
        return await self.client.search_suggestions(
            query=_text(query, "query"),
            limit=_limit(limit),
        )

    async def get_trending(
        self,
        *,
        country: str = "US",
        countries: str | None = None,
        limit: int = 20,
    ) -> JSON:
        limit = _limit(limit)
        if countries is not None and countries.strip():
            requested = [item.strip().upper() for item in countries.split(",") if item.strip()]
            if not requested:
                raise ToolInputError("countries must contain at least one country code")
            invalid = [code for code in requested if code not in TRENDING_COUNTRIES]
            if invalid:
                raise ToolInputError(
                    f"Unsupported country code(s): {', '.join(invalid)}. "
                    f"Supported codes: {', '.join(TRENDING_COUNTRIES)}"
                )
            return await self.client.get_trending(
                country=country,
                countries=",".join(requested),
                limit=limit,
            )
        return await self.client.get_trending(country=_trending_country(country), limit=limit)

    async def get_top_queries(
        self,
        *,
        limit: int = 20,
        country: str | None = None,
        days: int | None = None,
    ) -> JSON:
        limit = _limit(limit)
        if country is not None and country.strip():
            country = _country_code(country)
        else:
            country = None
        if days is not None and not 1 <= days <= 3650:
            raise ToolInputError("days must be between 1 and 3650")
        return await self.client.get_top_queries(limit=limit, country=country, days=days)

    async def get_trending_by_country(self, *, limit: int = 10) -> JSON:
        return await self.client.get_trending_by_country(limit=_limit(limit))

    async def compare_trending_vs_queries(self, *, country: str = "US", limit: int = 10) -> JSON:
        return await self.client.get_trending_vs_queries(
            country=_trending_country(country),
            limit=_limit(limit),
        )

    async def get_trending_intersection(self, *, country: str = "US", limit: int = 10) -> JSON:
        return await self.client.get_trending_intersection(
            country=_trending_country(country),
            limit=_limit(limit),
        )

    async def search_jiosaavn(self, *, query: str) -> JSON:
        return await self.client.search_jiosaavn(query=_text(query, "query"))

    async def get_jiosaavn_stream(self, *, song_link: str) -> JSON:
        return await self.client.get_jiosaavn_stream(song_link=_text(song_link, "song_link", max_length=2048))

    async def get_health(self, *, ready: bool = False) -> JSON:
        return await self.client.get_health(ready=ready)

    async def get_cache_stats(self) -> JSON:
        return await self.client.get_cache_stats()
