"""Command-line entry point for the Lyrica MCP server."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence

from dotenv import load_dotenv

from . import TARGET_API_VERSION, __version__
from .client import LyricaAPIError, LyricaClient
from .config import DEFAULT_BASE_URL, TRANSPORTS, ConfigurationError, Settings
from .server import create_server


def _parser(defaults: Settings) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lyrica-mcp",
        description=(
            f"MCP server for the stable Lyrica v{TARGET_API_VERSION} REST API. "
            "Runs over stdio by default, or Streamable HTTP with --transport streamable-http."
        ),
    )
    parser.add_argument("--version", action="version", version=f"lyrica-mcp {__version__}")
    parser.add_argument(
        "--base-url",
        default=defaults.base_url,
        help=f"Lyrica API base URL (default: {defaults.base_url}, env: LYRICA_API_URL)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=defaults.timeout,
        help=f"HTTP timeout in seconds (default: {defaults.timeout:g}, env: LYRICA_TIMEOUT)",
    )
    parser.add_argument(
        "--transport",
        choices=TRANSPORTS,
        default=defaults.transport,
        help=f"MCP transport (default: {defaults.transport}, env: LYRICA_MCP_TRANSPORT)",
    )
    parser.add_argument(
        "--host",
        default=defaults.host,
        help=f"HTTP bind host for streamable-http (default: {defaults.host}, env: LYRICA_MCP_HOST)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=defaults.port,
        help=f"HTTP port for streamable-http (default: {defaults.port}, env: LYRICA_MCP_PORT)",
    )
    parser.add_argument(
        "--http-path",
        default=defaults.http_path,
        help=f"Streamable HTTP endpoint path (default: {defaults.http_path}, env: LYRICA_MCP_PATH)",
    )
    parser.add_argument(
        "--json-response",
        action=argparse.BooleanOptionalAction,
        default=defaults.json_response,
        help="Return JSON responses instead of SSE on the Streamable HTTP transport.",
    )
    parser.add_argument(
        "--log-level",
        default=defaults.log_level,
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        help=f"Log level (default: {defaults.log_level}, env: LYRICA_MCP_LOG_LEVEL)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check connectivity to the Lyrica API and exit instead of starting the MCP server.",
    )
    parser.add_argument(
        "--ensure-api",
        action="store_true",
        help="Start the repository Docker Compose API if needed, wait until ready, then start MCP.",
    )
    return parser


async def _check(settings: Settings) -> int:
    async with LyricaClient(settings) as client:
        try:
            health = await client.get_health(ready=True)
        except LyricaAPIError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    print(json.dumps(health, indent=2, ensure_ascii=False))
    return 0


async def _api_ready(settings: Settings) -> bool:
    async with LyricaClient(settings) as client:
        try:
            await client.get_health(ready=True)
            return True
        except LyricaAPIError:
            return False


async def _ensure_api(settings: Settings) -> bool:
    if await _api_ready(settings):
        return True

    repo_root = Path(__file__).resolve().parents[2]
    compose_file = repo_root / "docker-compose.yml"
    if not compose_file.is_file():
        print(f"error: docker compose file not found: {compose_file}", file=sys.stderr)
        return False

    try:
        subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "up", "-d"],
            cwd=repo_root,
            check=True,
            timeout=300,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"error: could not start Lyrica API with Docker Compose: {exc}", file=sys.stderr)
        return False

    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        if await _api_ready(settings):
            return True
        await asyncio.sleep(2)
    print(f"error: Lyrica API did not become ready at {settings.base_url}", file=sys.stderr)
    return False


def main(argv: Sequence[str] | None = None) -> int:
    # `.env` next to the package (mcp_server/.env) wins over one in the cwd,
    # but real environment variables always win over both.
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    load_dotenv()

    try:
        settings = Settings.from_env()
        args = _parser(settings).parse_args(argv)
        settings = settings.with_overrides(
            base_url=args.base_url,
            timeout=args.timeout,
            transport=args.transport,
            host=args.host,
            port=args.port,
            http_path=args.http_path,
            json_response=args.json_response,
            log_level=args.log_level,
        )
    except ConfigurationError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2

    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    if args.check:
        return asyncio.run(_check(settings))

    if args.ensure_api and settings.base_url == DEFAULT_BASE_URL and not os.getenv("LYRICA_API_URL"):
        settings = settings.with_overrides(base_url="http://127.0.0.1:7860")

    if args.ensure_api and not asyncio.run(_ensure_api(settings)):
        return 1

    server = create_server(settings)
    if settings.transport == "stdio":
        server.run("stdio")
    else:
        server.run(
            "streamable-http",
            host=settings.host,
            port=settings.port,
            streamable_http_path=settings.http_path,
            json_response=settings.json_response,
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
