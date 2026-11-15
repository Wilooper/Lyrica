from __future__ import annotations

import pytest

from lyrica_mcp.operations import LyricaOperations, ToolInputError


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def __getattr__(self, name: str):
        async def call(**kwargs):
            self.calls.append((name, kwargs))
            return {"method": name, "kwargs": kwargs}

        return call


@pytest.fixture
def ops() -> tuple[LyricaOperations, FakeClient]:
    client = FakeClient()
    return LyricaOperations(client), client


async def test_word_implies_timestamps(ops) -> None:
    operations, client = ops
    await operations.get_lyrics(artist="A", song="B", word=True)

    method, kwargs = client.calls[0]
    assert method == "get_lyrics"
    assert kwargs["timestamps"] is True
    assert kwargs["word"] is True


async def test_syllabus_implies_timestamps(ops) -> None:
    operations, client = ops
    await operations.get_lyrics(artist=" A ", song=" B ", syllabus=True, country="gb")

    _, kwargs = client.calls[0]
    assert kwargs["artist"] == "A"
    assert kwargs["song"] == "B"
    assert kwargs["timestamps"] is True
    assert kwargs["country"] == "GB"


async def test_pass_through_requires_sequence(ops) -> None:
    operations, _ = ops
    with pytest.raises(ToolInputError, match="requires a non-empty sequence"):
        await operations.get_lyrics(artist="A", song="B", pass_through=True)


async def test_sequence_and_language_validation(ops) -> None:
    operations, client = ops
    await operations.get_lyrics(artist="A", song="B", sequence=" 2,7 ", language=" HI ")

    _, kwargs = client.calls[0]
    assert kwargs["sequence"] == "2,7"
    assert kwargs["language"] == "hi"


async def test_empty_and_oversized_text_rejected(ops) -> None:
    operations, _ = ops
    with pytest.raises(ToolInputError, match="artist must not be empty"):
        await operations.get_lyrics(artist="   ", song="B")
    with pytest.raises(ToolInputError, match="song must be at most 200"):
        await operations.get_lyrics(artist="A", song="x" * 201)


async def test_invalid_country_rejected(ops) -> None:
    operations, _ = ops
    with pytest.raises(ToolInputError, match="two-letter ISO country code"):
        await operations.get_lyrics(artist="A", song="B", country="USA")


async def test_top_queries_accepts_non_trending_country(ops) -> None:
    operations, client = ops
    await operations.get_top_queries(country="nl")

    assert client.calls[0][1] == {"limit": 20, "country": "NL", "days": None}


async def test_trending_rejects_unsupported_country(ops) -> None:
    operations, _ = ops
    with pytest.raises(ToolInputError, match="Unsupported trending country code"):
        await operations.get_trending(country="NL")


async def test_trending_single_country(ops) -> None:
    operations, client = ops
    await operations.get_trending(country="in", limit=5)

    _, kwargs = client.calls[0]
    assert kwargs == {"country": "IN", "limit": 5}


async def test_trending_multiple_countries(ops) -> None:
    operations, client = ops
    await operations.get_trending(countries="us, gb ,in", limit=3)

    _, kwargs = client.calls[0]
    assert kwargs == {"country": "US", "countries": "US,GB,IN", "limit": 3}


async def test_trending_invalid_multi_country(ops) -> None:
    operations, _ = ops
    with pytest.raises(ToolInputError, match="Unsupported country code"):
        await operations.get_trending(countries="US,ZZ")


async def test_top_queries_optional_filters(ops) -> None:
    operations, client = ops
    await operations.get_top_queries(limit=10)
    await operations.get_top_queries(limit=10, country="us", days=7)

    _, first = client.calls[0]
    _, second = client.calls[1]
    assert first == {"limit": 10, "country": None, "days": None}
    assert second == {"limit": 10, "country": "US", "days": 7}


async def test_limit_and_days_bounds(ops) -> None:
    operations, _ = ops
    with pytest.raises(ToolInputError, match="limit must be between"):
        await operations.search_suggestions(query="x", limit=0)
    with pytest.raises(ToolInputError, match="days must be between"):
        await operations.get_top_queries(days=0)


async def test_analytics_country_validation(ops) -> None:
    operations, client = ops
    await operations.compare_trending_vs_queries(country="ca", limit=4)
    await operations.get_trending_intersection(country="mx", limit=4)

    assert client.calls[0][1] == {"country": "CA", "limit": 4}
    assert client.calls[1][1] == {"country": "MX", "limit": 4}


async def test_jiosaavn_validation(ops) -> None:
    operations, client = ops
    await operations.search_jiosaavn(query=" Kesariya ")
    await operations.get_jiosaavn_stream(song_link="https://example.com/song")

    assert client.calls[0][1] == {"query": "Kesariya"}
    assert client.calls[1][1] == {"song_link": "https://example.com/song"}


async def test_health_ready_flag(ops) -> None:
    operations, client = ops
    await operations.get_health(ready=True)

    assert client.calls[0] == ("get_health", {"ready": True})
