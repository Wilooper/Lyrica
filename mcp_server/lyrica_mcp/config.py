"""Runtime configuration for the Lyrica MCP server."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from urllib.parse import urlparse

DEFAULT_BASE_URL = "http://127.0.0.1:9999"
DEFAULT_TIMEOUT = 90.0
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_HTTP_PATH = "/mcp"
DEFAULT_TRANSPORT = "stdio"
DEFAULT_LOG_LEVEL = "INFO"

TRANSPORTS = ("stdio", "streamable-http")
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class ConfigurationError(ValueError):
    """Raised when the MCP server is configured with an invalid value."""


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return default if value is None or not value.strip() else value.strip()


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number, got {raw!r}") from exc
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} must be between {minimum} and {maximum}, got {value}")
    return value


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer, got {raw!r}") from exc
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} must be between {minimum} and {maximum}, got {value}")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated settings for one MCP server instance."""

    base_url: str = DEFAULT_BASE_URL
    timeout: float = DEFAULT_TIMEOUT
    transport: str = DEFAULT_TRANSPORT
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    http_path: str = DEFAULT_HTTP_PATH
    log_level: str = DEFAULT_LOG_LEVEL
    json_response: bool = False

    def __post_init__(self) -> None:
        base_url = self.base_url.strip().rstrip("/")
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ConfigurationError(
                "LYRICA_API_URL must be an absolute http(s) URL, "
                f"for example {DEFAULT_BASE_URL!r}; got {self.base_url!r}"
            )
        if parsed.query or parsed.fragment:
            raise ConfigurationError("LYRICA_API_URL must not contain a query string or fragment")

        if not 1 <= self.timeout <= 600:
            raise ConfigurationError("LYRICA_TIMEOUT must be between 1 and 600 seconds")
        if self.transport not in TRANSPORTS:
            raise ConfigurationError(f"transport must be one of {TRANSPORTS}, got {self.transport!r}")
        if not 1 <= self.port <= 65535:
            raise ConfigurationError("port must be between 1 and 65535")
        if not self.http_path.startswith("/"):
            raise ConfigurationError("http_path must start with '/'")
        if self.log_level.upper() not in LOG_LEVELS:
            raise ConfigurationError(f"log_level must be one of {LOG_LEVELS}, got {self.log_level!r}")

        object.__setattr__(self, "base_url", base_url)
        object.__setattr__(self, "host", self.host.strip() or DEFAULT_HOST)
        object.__setattr__(self, "log_level", self.log_level.upper())

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from LYRICA_* environment variables."""
        transport = _env("LYRICA_MCP_TRANSPORT", DEFAULT_TRANSPORT).lower()
        if transport in {"http", "streamable_http", "streamablehttp"}:
            transport = "streamable-http"
        return cls(
            base_url=_env("LYRICA_API_URL", DEFAULT_BASE_URL),
            timeout=_env_float("LYRICA_TIMEOUT", DEFAULT_TIMEOUT, 1, 600),
            transport=transport,
            host=_env("LYRICA_MCP_HOST", DEFAULT_HOST),
            port=_env_int("LYRICA_MCP_PORT", DEFAULT_PORT, 1, 65535),
            http_path=_env("LYRICA_MCP_PATH", DEFAULT_HTTP_PATH),
            log_level=_env("LYRICA_MCP_LOG_LEVEL", DEFAULT_LOG_LEVEL),
            json_response=_env("LYRICA_MCP_JSON_RESPONSE", "false").lower() in {"1", "true", "yes", "on"},
        )

    def with_overrides(self, **overrides: object) -> "Settings":
        """Return a copy with non-None overrides applied (used by the CLI)."""
        clean = {key: value for key, value in overrides.items() if value is not None}
        return replace(self, **clean)
