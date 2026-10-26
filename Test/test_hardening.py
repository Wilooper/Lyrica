"""Regression tests for production-hardening fixes (no network required)."""

from __future__ import annotations

import asyncio
import os
import threading

import pytest

os.environ.setdefault("RATELIMIT_ENABLED", "false")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("ADMIN_KEY", "test-admin-key")

from src.app import create_app  # noqa: E402
from src.cache import load_from_cache, make_cache_key, save_to_cache, CACHE_DIR  # noqa: E402
from src.router import _sanitize_text, run_async  # noqa: E402
from src.trending_analytics import TrendingAnalyticsEngine  # noqa: E402


@pytest.fixture(scope="module")
def client():
    app = create_app()
    app.config["TESTING"] = True
    app.config["RATELIMIT_ENABLED"] = False
    return app.test_client()


def test_sanitize_text_strips_control_chars():
    assert _sanitize_text("a\x00b\x1fc") == "a b c"
    assert _sanitize_text("  a   b  ") == "a   b"


def test_cache_key_accepts_string_or_list_sequence():
    as_string = make_cache_key("The  Beatles", "Hey Jude", False, "1,2", False, False, False)
    as_list = make_cache_key("the beatles", "hey  jude", False, [1, 2], False, False, False)
    assert as_string == as_list


def test_invalid_integer_params_do_not_500(client):
    for path in (
        "/trending/?limit=abc",
        "/analytics/top-queries/?limit=nope&days=never",
        "/analytics/trending-by-country/?limit=-5",
        "/suggestion?q=x&limit=abc",
    ):
        response = client.get(path)
        assert response.status_code != 500, path


def test_oversized_input_is_rejected(client):
    response = client.get("/lyrics/?artist=" + ("a" * 500) + "&song=x")
    assert response.status_code == 400
    assert "at most" in response.get_json()["error"]["message"]


def test_admin_cache_clear_is_post_only(client):
    assert client.get("/admin/cache/clear").status_code == 405
    assert client.post("/admin/cache/clear").status_code == 403
    ok = client.post(
        "/admin/cache/clear", headers={"X-ADMIN-KEY": "test-admin-key"}
    )
    assert ok.status_code == 200


def test_suggestion_upstream_failure_returns_502(client, monkeypatch):
    import src.router as router

    def boom(*args, **kwargs):
        raise RuntimeError("upstream down")

    monkeypatch.setattr(router._SUGGESTION_CLIENT, "get", boom)
    response = client.get("/suggestion?q=test")
    assert response.status_code == 502
    assert response.get_json()["status"] == "error"


def test_clear_cache_clears_auxiliary_caches():
    from src.cache import clear_cache
    from src.metadata_extractor import _metadata_cache_get, _metadata_cache_set
    from src.translation_cache import (
        load_translation_cache,
        make_translation_cache_key,
        save_translation_cache,
    )

    trans_key = make_translation_cache_key(
        "Artist", "Song", "lrclib", "es", True, False, False
    )
    save_translation_cache(trans_key, {"status": "success"})
    assert load_translation_cache(trans_key) is not None

    _metadata_cache_set("artist|song", {"success": True})
    result = clear_cache()

    assert load_translation_cache(trans_key) is None
    assert _metadata_cache_get("artist|song") is None
    assert result["memory_cleared"] is True
    assert result["translation_cache"]["disk_files_removed"] >= 0


def test_cache_survives_unicode_and_atomic_write(tmp_path, monkeypatch):
    key = make_cache_key("歌手", "歌", False, None, False, False, False)
    payload = {"status": "success", "data": {"lyrics": "日本語の歌詞\n"}}
    save_to_cache(key, payload)
    assert load_from_cache(key) == payload
    # No temporary files should be left behind by the atomic writer.
    leftovers = [f for f in os.listdir(CACHE_DIR) if f.startswith(".lyrica-")]
    assert leftovers == []


def test_run_async_reuses_loop_and_maps_timeout():
    async def value():
        return 7

    async def slow():
        await asyncio.sleep(2)

    assert run_async(value(), timeout=2) == 7
    assert run_async(value(), timeout=2) == 7
    with pytest.raises(TimeoutError):
        run_async(slow(), timeout=0.05)


def test_run_async_is_thread_safe():
    async def value():
        return 1

    results: list[int] = []
    lock = threading.Lock()

    def worker():
        result = run_async(value(), timeout=2)
        with lock:
            results.append(result)

    threads = [threading.Thread(target=worker) for _ in range(32)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results == [1] * 32


def test_analytics_counters_are_bounded():
    engine = TrendingAnalyticsEngine(cache_ttl_hours=1)
    engine._max_unique_queries = 50  # force an aggressive rebuild threshold
    for i in range(500):
        engine.record_user_query("u", f"artist {i} - song {i}", "US")

    # Counters may briefly exceed the threshold, but never the number of
    # recently retained queries (the rebuild source).
    assert len(engine.query_cache) <= max(len(engine.user_queries), engine._max_unique_queries)
    assert len(engine.user_queries) == 500
    assert engine.get_top_queries(limit=5)


def test_health_is_lightweight(client):
    response = client.get("/health")
    body = response.get_json()
    assert response.status_code == 200
    assert body["status"] == "healthy"
    assert body["service"] == "Lyrica"
    assert response.headers.get("X-Request-ID")
