"""Shared pytest configuration for the Lyrica test suite.

The async integration tests require ``pytest-asyncio`` (listed in
``requirements-dev.txt``). When that plugin is not installed, skip only the
async tests with an actionable message instead of failing the whole run with
"async def functions are not natively supported".
"""

import inspect
import os

# These must be set before any test module imports ``src.config``, because the
# config module reads its values once at import time. Setting them inside a
# test module only works when that module happens to be collected first.
os.environ.setdefault("ADMIN_KEY", "test-admin-key")
os.environ.setdefault("RATELIMIT_ENABLED", "false")
os.environ.setdefault("LOG_LEVEL", "WARNING")

import pytest

try:  # pragma: no cover - depends on the local environment
    import pytest_asyncio  # noqa: F401

    _HAS_PYTEST_ASYNCIO = True
except ImportError:  # pragma: no cover
    _HAS_PYTEST_ASYNCIO = False


@pytest.fixture(scope="session", autouse=True)
def _finalize_event_loops():
    """Collect unreferenced loops while their selector FDs are still valid.

    Without this, CPython can tear down file descriptors before garbage
    collecting an event loop, which produces a noisy (and harmless)
    ``ValueError: Invalid file descriptor: -1`` at interpreter shutdown.
    """
    yield
    import gc

    try:
        from src.router import _close_thread_loops

        _close_thread_loops()
    except Exception:
        pass
    gc.collect()


def pytest_collection_modifyitems(config, items):
    if _HAS_PYTEST_ASYNCIO:
        return

    skip_marker = pytest.mark.skip(
        reason="pytest-asyncio is not installed — pip install -r requirements-dev.txt"
    )
    for item in items:
        if inspect.iscoroutinefunction(getattr(item, "function", None)):
            item.add_marker(skip_marker)
