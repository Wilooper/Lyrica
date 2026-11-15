from __future__ import annotations

import json

import httpx
import pytest
from mcp import Client

from lyrica_mcp.client import LyricaClient
from lyrica_mcp.config import Settings
from lyrica_mcp.constants import TOOL_NAMES
from lyrica_mcp.server import create_server


def _json_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    params = dict(request.url.params)
    if path == "/health/ready":
        return httpx.Response(200, json={"status": "ready", "version": "1.5.0", "redis": "connected"})
    if path == "/lyrics/":
        return httpx.Response(200, json={"status": "success", "path": path, "params": params})
    return httpx.Response(200, json={"status": "success", "path": path, "params": params})


@pytest.fixture
def server():
    settings = Settings(base_url="http://lyrica.test:9999")
    transport = httpx.MockTransport(_json_handler)
    return create_server(
        settings,
        client_factory=lambda: LyricaClient(settings, transport=transport),
    )


async def test_all_tools_are_registered(server) -> None:
    async with Client(server) as client:
        listing = await client.list_tools()

    names = {tool.name for tool in listing.tools}
    assert names == set(TOOL_NAMES)
    assert len(names) == 12


async def test_resources_are_registered_and_readable(server) -> None:
    async with Client(server) as client:
        resources = await client.list_resources()
        info = await client.read_resource("lyrica://api/info")
        providers = await client.read_resource("lyrica://providers")

    uris = {str(resource.uri) for resource in resources.resources}
    assert uris == {"lyrica://api/info", "lyrica://providers"}

    info_data = json.loads(info.contents[0].text)
    assert info_data["target_api"]["version"] == "1.5.0"
    assert info_data["target_api"]["base_url"] == "http://lyrica.test:9999"
    assert "lyrica_get_lyrics" in info_data["tools"]

    provider_data = json.loads(providers.contents[0].text)
    assert len(provider_data["providers"]) == 8
    assert provider_data["default_sequence"][0] == "lrclib"


async def test_prompts_are_registered(server) -> None:
    async with Client(server) as client:
        prompts = await client.list_prompts()
        result = await client.get_prompt(
            "fetch_lyrics_prompt",
            {"artist": "Coldplay", "song": "Yellow", "sync": "word"},
        )

    names = {prompt.name for prompt in prompts.prompts}
    assert names == {"fetch_lyrics_prompt", "trending_prompt"}
    text = result.messages[0].content.text
    assert "word=true" in text
    assert "Coldplay" in text


async def test_lyrics_tool_hits_v1_endpoint(server) -> None:
    async with Client(server) as client:
        result = await client.call_tool(
            "lyrica_get_lyrics",
            {"artist": "Coldplay", "song": "Yellow", "word": True, "country": "gb"},
        )

    assert result.is_error is False
    structured = result.structured_content
    assert structured["path"] == "/lyrics/"
    assert structured["params"]["artist"] == "Coldplay"
    assert structured["params"]["song"] == "Yellow"
    assert structured["params"]["word"] == "true"
    assert structured["params"]["timestamps"] == "true"
    assert structured["params"]["country"] == "GB"


async def test_health_tool_uses_ready_endpoint(server) -> None:
    async with Client(server) as client:
        result = await client.call_tool("lyrica_get_health", {"ready": True})

    assert result.is_error is False
    assert result.structured_content["status"] == "ready"
    assert result.structured_content["version"] == "1.5.0"


async def test_validation_error_is_tool_error(server) -> None:
    async with Client(server) as client:
        result = await client.call_tool(
            "lyrica_get_lyrics",
            {"artist": "Coldplay", "song": "Yellow", "pass_through": True},
        )

    assert result.is_error is True
    assert "requires a non-empty sequence" in result.content[0].text


async def test_upstream_error_is_tool_error(server) -> None:
    settings = Settings(base_url="http://lyrica.test:9999")
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            404,
            json={"status": "error", "error": {"message": "Lyrics not found"}},
        )
    )
    error_server = create_server(
        settings,
        client_factory=lambda: LyricaClient(settings, transport=transport),
    )

    async with Client(error_server) as client:
        result = await client.call_tool(
            "lyrica_get_lyrics",
            {"artist": "Nobody", "song": "Nothing"},
        )

    assert result.is_error is True
    text = result.content[0].text
    assert "HTTP 404" in text
    assert "Lyrics not found" in text
