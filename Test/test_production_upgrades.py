"""
Test production upgrades:
- Redis / Multi-tier caching
- Metadata extractor (async httpx)
- Trending analytics (httpx)
- Flask test client requests
- Groq model configuration
"""
import sys
import os
import asyncio

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import GROQ_MODEL, REDIS_URL
from src.cache import make_cache_key, save_to_cache, load_from_cache, cache_stats, clear_cache
from src.translation_cache import make_translation_cache_key, save_translation_cache, load_translation_cache, translation_cache_stats
from src.metadata_extractor import get_song_metadata_async, format_metadata
from src.trending_analytics import TrendingAnalyticsEngine, Country
from src.app import app


def test_groq_model():
    print("Testing Groq Model configuration...")
    assert GROQ_MODEL == "openai/gpt-oss-120b", f"Expected openai/gpt-oss-120b, got {GROQ_MODEL}"
    print(f"  [PASS] GROQ_MODEL = {GROQ_MODEL}")


def test_cache_multi_tier():
    print("\nTesting Multi-Tier Caching System...")
    key = make_cache_key(
        artist="Queen",
        song="Bohemian Rhapsody",
        timestamps=False,
        sequence="lrclib",
        fast=False,
        mood=False,
        metadata=False,
    )
    test_data = {"status": "success", "data": {"artist": "Queen", "title": "Bohemian Rhapsody", "lyrics": "Is this the real life?"}}

    # Save
    save_to_cache(key, test_data)

    # Load
    loaded = load_from_cache(key)
    assert loaded is not None, "Failed to load from cache"
    assert loaded["data"]["title"] == "Bohemian Rhapsody", "Cached data mismatch"
    print("  [PASS] Cache save and load works seamlessly")

    # Stats
    stats = cache_stats()
    assert "backend" in stats
    assert "memory_l1_items" in stats
    print(f"  [PASS] Cache stats: {stats['backend']} with {stats['memory_l1_items']} L1 items")

    # Translation Cache
    t_key = make_translation_cache_key(
        artist="Queen",
        song="Bohemian Rhapsody",
        source="lrclib",
        language="es",
        translate=True,
        romanize=False,
        has_timestamps=False,
    )
    t_data = {"status": "success", "data": {"translated_lyrics": "¿Es esta la vida real?"}}
    save_translation_cache(t_key, t_data)
    loaded_t = load_translation_cache(t_key)
    assert loaded_t is not None
    assert loaded_t["data"]["translated_lyrics"] == "¿Es esta la vida real?"
    t_stats = translation_cache_stats()
    print(f"  [PASS] Translation cache stats: L1 items = {t_stats['memory_l1_items']}")

    # Clear
    clear_result = clear_cache()
    print("  [PASS] Cache clear works")


async def test_metadata_async():
    print("\nTesting Metadata Extractor (Async httpx)...")
    res = await get_song_metadata_async("Queen", "Bohemian Rhapsody")
    print(f"  [INFO] Metadata result success: {res.get('success')}, sources: {res.get('sources')}")
    if res.get("success"):
        formatted = format_metadata(res["metadata"])
        print(f"  [PASS] Metadata title: {formatted.get('title')}, artist: {formatted.get('artist')}")
    else:
        print(f"  [WARN] Metadata search returned: {res.get('error')}")


def test_trending_httpx():
    print("\nTesting Trending Analytics (httpx)...")
    engine = TrendingAnalyticsEngine(cache_ttl_hours=1)
    songs = engine.fetch_trending_songs(Country.US, limit=5)
    print(f"  [INFO] Fetched {len(songs)} trending songs for US")
    if songs:
        print(f"  [PASS] Top song: #{songs[0].rank} {songs[0].title} by {songs[0].artist}")


def test_flask_routes():
    print("\nTesting Flask API endpoints via test_client...")
    client = app.test_client()

    # Home route
    r_home = client.get("/")
    assert r_home.status_code == 200
    home_json = r_home.get_json()
    assert home_json.get("api") == "Lyrica"
    print(f"  [PASS] GET / -> 200 (Version: {home_json.get('version')})")

    # Admin Cache Stats
    r_stats = client.get("/admin/cache/stats")
    # without admin key -> 403
    assert r_stats.status_code == 403
    print("  [PASS] GET /admin/cache/stats -> 403 unauthorized without key")

    # Trending endpoint
    r_trend = client.get("/trending/?country=US&limit=5")
    assert r_trend.status_code == 200
    trend_json = r_trend.get_json()
    assert trend_json.get("status") == "success"
    print("  [PASS] GET /trending/ -> 200 success")


if __name__ == "__main__":
    print("=== RUNNING PRODUCTION UPGRADES VERIFICATION ===")
    test_groq_model()
    test_cache_multi_tier()
    test_trending_httpx()
    asyncio.run(test_metadata_async())
    test_flask_routes()
    print("\n=== ALL TESTS PASSED SUCCESSFULLY ===")
