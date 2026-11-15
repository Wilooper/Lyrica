"""Async HTTP client for the Lyrica v1.5.0 REST API."""

from __future__ import annotations

import logging
from typing import Any, Mapping

import httpx

from . import __version__
from .config import Settings

logger = logging.getLogger(__name__)

JSON = dict[str, Any]


class LyricaAPIError(RuntimeError):
    """A transport or upstream error returned by the Lyrica API."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        method: str | None = None,
        path: str | None = None,
        payload: Any = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.method = method
        self.path = path
        self.payload = payload
        super().__init__(self.__str__())

    def __str__(self) -> str:
        prefix = "Lyrica API"
        if self.status_code is not None:
            prefix += f" returned HTTP {self.status_code}"
        if self.method and self.path:
            prefix += f" during {self.method} /{self.path.lstrip('/')}"
        return f"{prefix}: {self.message}"

    def to_dict(self) -> JSON:
        return {
            "message": self.message,
            "status_code": self.status_code,
            "method": self.method,
            "path": self.path,
            "payload": self.payload,
        }


def _error_message(payload: Any, status_code: int) -> str:
    if isinstance(payload, Mapping):
        error = payload.get("error")
        if isinstance(error, Mapping):
            message = error.get("message")
            if message:
                return str(message)
        elif isinstance(error, str) and error:
            return error
        for key in ("message", "detail", "details"):
            value = payload.get(key)
            if value:
                return str(value)
    if isinstance(payload, str) and payload.strip():
        return payload.strip()[:500]
    return f"request failed with HTTP {status_code}"


def _clean_params(params: Mapping[str, Any] | None) -> dict[str, str]:
    """Serialize query parameters the way the Lyrica v1 API expects."""
    if not params:
        return {}
    cleaned: dict[str, str] = {}
    for key, value in params.items():
        if value is None or value == "":
            continue
        if isinstance(value, bool):
            cleaned[key] = "true" if value else "false"
        else:
            cleaned[key] = str(value)
    return cleaned


class LyricaClient:
    """Small typed wrapper around the public Lyrica v1.5.0 endpoints.

    The client is safe to share across concurrent MCP tool calls. One instance
    is created for the lifetime of the MCP server.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self._client = httpx.AsyncClient(
            base_url=f"{settings.base_url}/",
            timeout=httpx.Timeout(settings.timeout, connect=min(10.0, settings.timeout)),
            headers={
                "Accept": "application/json",
                "User-Agent": f"lyrica-mcp/{__version__}",
            },
            follow_redirects=True,
            transport=transport,
        )

    async def __aenter__(self) -> "LyricaClient":
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        timeout: float | None = None,
    ) -> JSON:
        request_path = path.lstrip("/")
        clean = _clean_params(params)
        try:
            response = await self._client.request(
                method,
                request_path,
                params=clean or None,
                timeout=timeout if timeout is not None else self.settings.timeout,
            )
        except httpx.TimeoutException as exc:
            raise LyricaAPIError(
                f"request timed out after {timeout or self.settings.timeout:g}s "
                "(is the Lyrica API reachable? try a longer LYRICA_TIMEOUT)",
                method=method,
                path=request_path,
            ) from exc
        except httpx.HTTPError as exc:
            raise LyricaAPIError(
                f"could not reach the Lyrica API at {self.settings.base_url}: {exc}",
                method=method,
                path=request_path,
            ) from exc

        try:
            payload = response.json()
            is_json = True
        except ValueError:
            text = response.text.strip()
            payload = {"message": text} if text else None
            is_json = False

        if response.status_code >= 400:
            raise LyricaAPIError(
                _error_message(payload, response.status_code),
                status_code=response.status_code,
                method=method,
                path=request_path,
                payload=payload,
            )

        if not is_json or not isinstance(payload, dict):
            raise LyricaAPIError(
                "expected a JSON object from the Lyrica API",
                status_code=response.status_code,
                method=method,
                path=request_path,
                payload=payload,
            )

        logger.debug("%s %s -> HTTP %s", method, request_path, response.status_code)
        return payload

    # ── Lyrics & metadata ────────────────────────────────────────────────

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
        timeout = max(self.settings.timeout, 180.0) if (translate or romanize) else self.settings.timeout
        return await self._request(
            "GET",
            "/lyrics/",
            params={
                "artist": artist,
                "song": song,
                "timestamps": timestamps,
                "word": word,
                "syllabus": syllabus,
                "translate": translate,
                "romanize": romanize,
                "language": language,
                "mood": mood,
                "metadata": metadata,
                "sequence": sequence,
                "fast": fast,
                "pass": pass_through,
                "country": country,
            },
            timeout=timeout,
        )

    async def get_metadata(self, *, artist: str, song: str) -> JSON:
        return await self._request(
            "GET",
            "/metadata/",
            params={"artist": artist, "song": song},
            timeout=max(self.settings.timeout, 60.0),
        )

    async def search_suggestions(self, *, query: str, limit: int = 10) -> JSON:
        return await self._request(
            "GET",
            "/suggestion",
            params={"q": query, "limit": limit},
            timeout=max(self.settings.timeout, 60.0),
        )

    # ── Trending & analytics ─────────────────────────────────────────────

    async def get_trending(
        self,
        *,
        country: str = "US",
        countries: str | None = None,
        limit: int = 20,
    ) -> JSON:
        return await self._request(
            "GET",
            "/trending/",
            params={"country": country, "countries": countries, "limit": limit},
            timeout=max(self.settings.timeout, 60.0),
        )

    async def get_top_queries(
        self,
        *,
        limit: int = 20,
        country: str | None = None,
        days: int | None = None,
    ) -> JSON:
        return await self._request(
            "GET",
            "/analytics/top-queries/",
            params={"limit": limit, "country": country, "days": days},
        )

    async def get_trending_by_country(self, *, limit: int = 10) -> JSON:
        return await self._request(
            "GET",
            "/analytics/trending-by-country/",
            params={"limit": limit},
        )

    async def get_trending_vs_queries(self, *, country: str = "US", limit: int = 10) -> JSON:
        return await self._request(
            "GET",
            "/analytics/trending-vs-queries/",
            params={"country": country, "limit": limit},
        )

    async def get_trending_intersection(self, *, country: str = "US", limit: int = 10) -> JSON:
        return await self._request(
            "GET",
            "/analytics/trending-intersection/",
            params={"country": country, "limit": limit},
        )

    # ── JioSaavn ─────────────────────────────────────────────────────────

    async def search_jiosaavn(self, *, query: str) -> JSON:
        return await self._request(
            "GET",
            "/api/jiosaavn/search",
            params={"q": query},
            timeout=max(self.settings.timeout, 60.0),
        )

    async def get_jiosaavn_stream(self, *, song_link: str) -> JSON:
        return await self._request(
            "GET",
            "/api/jiosaavn/play",
            params={"songLink": song_link},
            timeout=max(self.settings.timeout, 60.0),
        )

    # ── System ───────────────────────────────────────────────────────────

    async def get_health(self, *, ready: bool = False) -> JSON:
        return await self._request("GET", "/health/ready" if ready else "/health")

    async def get_cache_stats(self) -> JSON:
        return await self._request("GET", "/cache/stats")
