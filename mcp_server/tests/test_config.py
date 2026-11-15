from __future__ import annotations

import pytest

from lyrica_mcp.config import ConfigurationError, Settings


def test_defaults_are_valid() -> None:
    settings = Settings()
    assert settings.base_url == "http://127.0.0.1:9999"
    assert settings.transport == "stdio"
    assert settings.timeout == 90.0
    assert settings.port == 8000


def test_base_url_is_normalized() -> None:
    settings = Settings(base_url=" https://lyrica.example.com/api/ ")
    assert settings.base_url == "https://lyrica.example.com/api"


@pytest.mark.parametrize("url", ["localhost:9999", "ftp://example.com", "https://", "/relative"])
def test_invalid_base_url_rejected(url: str) -> None:
    with pytest.raises(ConfigurationError):
        Settings(base_url=url)


def test_query_string_rejected() -> None:
    with pytest.raises(ConfigurationError, match="query string"):
        Settings(base_url="https://example.com?x=1")


def test_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LYRICA_API_URL", "http://lyrica:7860/")
    monkeypatch.setenv("LYRICA_TIMEOUT", "42.5")
    monkeypatch.setenv("LYRICA_MCP_TRANSPORT", "http")
    monkeypatch.setenv("LYRICA_MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("LYRICA_MCP_PORT", "9000")
    monkeypatch.setenv("LYRICA_MCP_PATH", "/lyrica/mcp")
    monkeypatch.setenv("LYRICA_MCP_JSON_RESPONSE", "true")
    monkeypatch.setenv("LYRICA_MCP_LOG_LEVEL", "debug")

    settings = Settings.from_env()
    assert settings.base_url == "http://lyrica:7860"
    assert settings.timeout == 42.5
    assert settings.transport == "streamable-http"
    assert settings.host == "0.0.0.0"
    assert settings.port == 9000
    assert settings.http_path == "/lyrica/mcp"
    assert settings.json_response is True
    assert settings.log_level == "DEBUG"


def test_invalid_env_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LYRICA_TIMEOUT", "not-a-number")
    with pytest.raises(ConfigurationError):
        Settings.from_env()


def test_invalid_transport_rejected() -> None:
    with pytest.raises(ConfigurationError):
        Settings(transport="websocket")


def test_http_path_must_be_absolute() -> None:
    with pytest.raises(ConfigurationError):
        Settings(http_path="mcp")


def test_with_overrides_keeps_validation() -> None:
    settings = Settings().with_overrides(base_url="https://example.com/", port=9001)
    assert settings.base_url == "https://example.com"
    assert settings.port == 9001
    with pytest.raises(ConfigurationError):
        Settings().with_overrides(port=70000)
