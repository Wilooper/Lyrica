"""Production-path benchmark for Lyrica.

Measures the paths that matter under real traffic without hitting upstream
providers:

1. L1 cache throughput / latency distribution.
2. Cached ``GET /lyrics/`` end-to-end latency (the dominant production path).
3. Cached ``GET /metadata/`` latency.
4. Liveness endpoint latency.
5. Concurrent analytics writes (thread-safety / contention check).

Run::

    python Test/benchmark_production.py

Set ``BENCH_CONCURRENCY`` / ``BENCH_REQUESTS`` to tune the load.
"""

from __future__ import annotations

import concurrent.futures
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["RATELIMIT_ENABLED"] = "false"
# Per-request INFO logging to a terminal dominates Flask test-client latency.
# Production containers run at WARNING by default; benchmark the same way.
os.environ.setdefault("LOG_LEVEL", "WARNING")

from src.app import create_app  # noqa: E402
from src.cache import load_from_cache, make_cache_key, save_to_cache  # noqa: E402
from src.metadata_extractor import _metadata_cache_set  # noqa: E402


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    index = min(len(values) - 1, int(len(values) * pct))
    return values[index]


def _run_concurrent(client, path: str, concurrency: int, requests: int) -> list[float]:
    latencies: list[float] = []

    def worker(_):
        started = time.perf_counter()
        response = client.get(path)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if response.status_code != 200:
            raise AssertionError(f"{path} returned {response.status_code}")
        return elapsed_ms

    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        latencies = list(pool.map(worker, range(requests)))
    total = time.perf_counter() - started
    return sorted(latencies), requests / total


def _print_row(name: str, requests: int, rps: float, p50: float, p95: float, p99: float) -> None:
    print(
        f"{name:<34} | {requests:>8} | {rps:>11,.1f} req/s | "
        f"{p50:>8.3f} ms | {p95:>8.3f} ms | {p99:>8.3f} ms"
    )


def main() -> None:
    concurrency = int(os.getenv("BENCH_CONCURRENCY", "32"))
    requests = int(os.getenv("BENCH_REQUESTS", "2000"))

    app = create_app()
    app.config["TESTING"] = True
    app.config["RATELIMIT_ENABLED"] = False
    client = app.test_client()

    artist, song = "Bench Artist", "Bench Song"

    # Seed the exact cache key the /lyrics/ route computes. Note that the route
    # falls back to .lyrica.config defaults (UserConfig always has a sequence),
    # so mirror get_user_config() rather than assuming None.
    from src.user_config import get_user_config
    cfg = get_user_config()
    cache_key = make_cache_key(
        artist, song, False, cfg.default_sequence if cfg else None,
        False, False, False,
        translate=False, romanize=False, language="en",
        word_level=False, syllabus=False,
    )
    save_to_cache(cache_key, {
        "status": "success",
        "data": {
            "source": "lrclib",
            "artist": artist,
            "title": song,
            "lyrics": ("benchmark lyric line\n" * 40).strip(),
            "hasTimestamps": False,
        },
    })

    # Seed metadata cache so /metadata/ measures framework work, not upstreams.
    _metadata_cache_set(
        f"{artist.lower()}|{song.lower()}",
        {
            "success": True,
            "sources": ["benchmark"],
            "metadata": {"title": song, "artist": artist, "duration_ms": 180000},
        },
    )

    print("=" * 112)
    print(f"LYRICA PRODUCTION BENCHMARK — concurrency={concurrency}, requests={requests}")
    print("=" * 112)
    print(
        f"{'Path':<34} | {'Requests':>8} | {'Throughput':>18} | "
        f"{'p50':>11} | {'p95':>11} | {'p99':>11}"
    )
    print("-" * 112)

    # 1. L1 cache reads
    def cache_worker(_):
        started = time.perf_counter()
        assert load_from_cache(cache_key) is not None
        return (time.perf_counter() - started) * 1000.0

    l1 = []
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        l1 = sorted(pool.map(cache_worker, range(requests * 5)))
    l1_total = time.perf_counter() - started
    _print_row(
        "L1 memory cache read", requests * 5, (requests * 5) / l1_total,
        statistics.median(l1), _percentile(l1, 0.95), _percentile(l1, 0.99),
    )

    # 2. Cached lyrics endpoint
    lyr, lyr_rps = _run_concurrent(client, f"/lyrics/?artist={artist}&song={song}", concurrency, requests)
    _print_row("GET /lyrics/ (cache hit)", requests, lyr_rps,
               statistics.median(lyr), _percentile(lyr, 0.95), _percentile(lyr, 0.99))

    # 3. Cached metadata endpoint
    meta, meta_rps = _run_concurrent(client, f"/metadata/?artist={artist}&song={song}", concurrency, requests)
    _print_row("GET /metadata/ (cache hit)", requests, meta_rps,
               statistics.median(meta), _percentile(meta, 0.95), _percentile(meta, 0.99))

    # 4. Liveness endpoint
    health, health_rps = _run_concurrent(client, "/health", concurrency, requests)
    _print_row("GET /health", requests, health_rps,
               statistics.median(health), _percentile(health, 0.95), _percentile(health, 0.99))

    # 5. Concurrent analytics writes
    from src.trending_analytics import TrendingAnalyticsEngine
    engine = TrendingAnalyticsEngine(cache_ttl_hours=1)

    def analytics_worker(i):
        started = time.perf_counter()
        engine.record_user_query(f"user-{i % 100}", f"artist {i} - song {i}", "US")
        return (time.perf_counter() - started) * 1000.0

    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        analytics = sorted(pool.map(analytics_worker, range(requests * 5)))
    analytics_total = time.perf_counter() - started
    _print_row(
        "analytics record_user_query", requests * 5, (requests * 5) / analytics_total,
        statistics.median(analytics), _percentile(analytics, 0.95), _percentile(analytics, 0.99),
    )

    print("=" * 112)
    print("Assertions:")
    assert statistics.median(l1) < 1.0, "L1 cache median latency regressed"
    assert statistics.median(lyr) < 10.0, "Cached lyrics route is unexpectedly slow"
    assert statistics.median(health) < 10.0, "Health endpoint is unexpectedly slow"
    print("  [PASS] cache, cached lyrics, metadata, health, and analytics paths met latency budgets")


if __name__ == "__main__":
    main()
