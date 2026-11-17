from __future__ import annotations

import asyncio
import subprocess

from lyrica_mcp import __main__ as cli
from lyrica_mcp.config import Settings


def test_ensure_api_skips_compose_when_api_is_ready(monkeypatch):
    calls = []

    async def ready(_settings):
        calls.append("health")
        return True

    monkeypatch.setattr(cli, "_api_ready", ready)
    monkeypatch.setattr(cli.subprocess, "run", lambda *args, **kwargs: calls.append("compose"))

    assert asyncio.run(cli._ensure_api(Settings())) is True
    assert calls == ["health"]


def test_ensure_api_starts_compose_and_waits_for_readiness(monkeypatch):
    calls = []
    health_results = iter([False, True])

    async def ready(_settings):
        calls.append("health")
        return next(health_results)

    def run(command, **kwargs):
        calls.append((command, kwargs["cwd"]))
        return subprocess.CompletedProcess(command, 0)

    async def no_wait(_seconds):
        return None

    monkeypatch.setattr(cli, "_api_ready", ready)
    monkeypatch.setattr(cli.subprocess, "run", run)
    monkeypatch.setattr(cli.asyncio, "sleep", no_wait)

    assert asyncio.run(cli._ensure_api(Settings())) is True
    assert calls[0] == "health"
    assert calls[1][0][-2:] == ["up", "-d"]
    assert (calls[1][1] / "docker-compose.yml").is_file()
    assert calls[2] == "health"
