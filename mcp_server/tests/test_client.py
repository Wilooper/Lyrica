from __future__ import annotations

import httpx
import pytest

from lyrica_mcp.client import LyricaAPIError, LyricaClient
from lyrica_mcp.config import Settings


def _client(handler: httpx.MockTransport) -> LyricaClient:
    return LyricaClient(Settings(base_url="http://lyrica.test:9999"), transport=handler)


def _capture(response_factory):
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return response_factory(request)

    return handler, seen


async def test_lyrics_sends_expected_query_parameters() -> None:
    handler, seen = _capture(lambda request: httpx.Response(200, json={"status": "success", "data": {}}))
    async with _client(httpx.MockTransport(handler)) as client:
        result = await client.get_lyrics(
            artist="Coldplay",
            song="Yellow",
            timestamps=True,
            word=True,
            translate=True,
            romanize=True,
            language="es",
            mood=True,
            metadata=True,
            sequence="2,7",
            fast=True,
            pass_through=True,
            country="GB",
        )

    assert result == {"status": "success", "data": {}}
    request = seen[0]
    assert request.method == "GET"
    assert request.url.path == "/lyrics/"
    params = dict(request.url.params)
    assert params == {
        "artist": "Coldplay",
        "song": "Yellow",
        "timestamps": "true",
        "word": "true",
        "syllabus": "false",
        "translate": "true",
        "romanize": "true",
        "language": "es",
        "mood": "true",
        "metadata": "true",
        "sequence": "2,7",
        "fast": "true",
        "pass": "true",
        "country": "GB",
    }


async def test_none_values_are_omitted() -> None:
    handler, seen = _capture(lambda request: httpx.Response(200, json={"status": "success"}))
    async with _client(httpx.MockTransport(handler)) as client:
        await client.get_top_queries(limit=5, country=None, days=None)

    params = dict(seen[0].url.params)
    assert params == {"limit": "5"}
    assert seen[0].url.path == "/analytics/top-queries/"


async def test_metadata_and_suggestion_paths() -> None:
    handler, seen = _capture(lambda request: httpx.Response(200, json={"status": "success"}))
    async with _client(httpx.MockTransport(handler)) as client:
        await client.get_metadata(artist="Queen", song="Bohemian Rhapsody")
        await client.search_suggestions(query="Imagine", limit=3)

    assert seen[0].url.path == "/metadata/"
    assert dict(seen[0].url.params) == {"artist": "Queen", "song": "Bohemian Rhapsody"}
    assert seen[1].url.path == "/suggestion"
    assert dict(seen[1].url.params) == {"q": "Imagine", "limit": "3"}


async def test_jiosaavn_paths() -> None:
    handler, seen = _capture(lambda request: httpx.Response(200, json={"status": "success"}))
    async with _client(httpx.MockTransport(handler)) as client:
        await client.search_jiosaavn(query="Kesariya")
        await client.get_jiosaavn_stream(song_link="https://www.jiosaavn.com/song/abc")

    assert seen[0].url.path == "/api/jiosaavn/search"
    assert dict(seen[0].url.params) == {"q": "Kesariya"}
    assert seen[1].url.path == "/api/jiosaavn/play"
    assert dict(seen[1].url.params) == {"songLink": "https://www.jiosaavn.com/song/abc"}


async def test_health_and_cache_paths() -> None:
    handler, seen = _capture(lambda request: httpx.Response(200, json={"status": "healthy"}))
    async with _client(httpx.MockTransport(handler)) as client:
        await client.get_health()
        await client.get_health(ready=True)
        await client.get_cache_stats()

    assert [request.url.path for request in seen] == ["/health", "/health/ready", "/cache/stats"]


async def test_error_envelope_becomes_api_error() -> None:
    payload = {"status": "error", "error": {"message": "Lyrics not found across all providers"}}
    handler, _ = _capture(lambda request: httpx.Response(404, json=payload))
    async with _client(httpx.MockTransport(handler)) as client:
        with pytest.raises(LyricaAPIError) as exc_info:
            await client.get_lyrics(artist="Nobody", song="Nothing")

    error = exc_info.value
    assert error.status_code == 404
    assert "Lyrics not found across all providers" in str(error)
    assert error.payload == payload


async def test_plain_text_error_uses_status_message() -> None:
    handler, _ = _capture(lambda request: httpx.Response(502, text="upstream exploded"))
    async with _client(httpx.MockTransport(handler)) as client:
        with pytest.raises(LyricaAPIError, match="upstream exploded"):
            await client.get_trending()


async def test_timeout_becomes_api_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    async with _client(httpx.MockTransport(handler)) as client:
        with pytest.raises(LyricaAPIError, match="timed out"):
            await client.get_lyrics(artist="A", song="B")


async def test_connection_error_becomes_api_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    async with _client(httpx.MockTransport(handler)) as client:
        with pytest.raises(LyricaAPIError, match="could not reach the Lyrica API"):
            await client.get_health()


async def test_non_json_success_is_rejected() -> None:
    handler, _ = _capture(lambda request: httpx.Response(200, text="<html>not json</html>"))
    async with _client(httpx.MockTransport(handler)) as client:
        with pytest.raises(LyricaAPIError, match="expected a JSON object"):
            await client.get_cache_stats()


async def test_non_object_json_is_rejected() -> None:
    handler, _ = _capture(lambda request: httpx.Response(200, json=[1, 2, 3]))
    async with _client(httpx.MockTransport(handler)) as client:
        with pytest.raises(LyricaAPIError, match="expected a JSON object"):
            await client.get_cache_stats()
