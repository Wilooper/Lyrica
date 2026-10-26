# Testing & Benchmarking Guide

Lyrica includes a comprehensive automated verification suite located in the [`Test/`](https://github.com/Wilooper/Lyrica/tree/main/Test) directory.

---

## Test Suite Catalog

| Test File | Category | Focus |
|---|:---:|---|
| [`Test/run_all_tests.py`](https://github.com/Wilooper/Lyrica/blob/main/Test/run_all_tests.py) | **Master Runner** | Executes all test suites and generates a consolidated status report |
| [`Test/test_real_genius.py`](https://github.com/Wilooper/Lyrica/blob/main/Test/test_real_genius.py) | **Integration** | Live HTTP extraction from Genius against real-world songs (`The Weeknd`, `Queen`) |
| [`Test/test_performance.py`](https://github.com/Wilooper/Lyrica/blob/main/Test/test_performance.py) | **Benchmark** | High-concurrency stress test measuring RPS, p50, p95, and p99 latency |
| [`Test/test_genius_parser.py`](https://github.com/Wilooper/Lyrica/blob/main/Test/test_genius_parser.py) | **Unit** | Validates tag-depth tracking parser and ad/badge exclusion |
| [`Test/test_production_upgrades.py`](https://github.com/Wilooper/Lyrica/blob/main/Test/test_production_upgrades.py) | **System** | Multi-tier caching, Redis/disk, metadata aggregation, trending analytics, and route auth |
| [`Test/test_hardening.py`](https://github.com/Wilooper/Lyrica/blob/main/Test/test_hardening.py) | **Regression** | Production hardening: input bounds, cache-key normalization, atomic writes, admin auth, async bridge, analytics bounds |
| [`Test/benchmark_production.py`](https://github.com/Wilooper/Lyrica/blob/main/Test/benchmark_production.py) | **Benchmark** | Cached `/lyrics/`, `/metadata/`, `/health`, L1 cache, and concurrent analytics writes |
| [`Test/conftest.py`](https://github.com/Wilooper/Lyrica/blob/main/Test/conftest.py) | **Fixtures** | Shared environment defaults; skips async tests when `pytest-asyncio` is unavailable |

> `Test/test_performance.py` is a standalone script. The other modern tests use
> pytest fixtures, so run them with `pytest` rather than `python <file>`.

## Running the pytest Suite

```bash
pip install -r requirements-dev.txt   # pytest, pytest-asyncio, ruff
python -m pytest Test/ -q
```

Use a virtual environment when the system Python is externally managed
(PEP 668):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest Test/ -q
```

## Running the Production Benchmark

```bash
python Test/benchmark_production.py
# Tune the load:
BENCH_CONCURRENCY=64 BENCH_REQUESTS=5000 python Test/benchmark_production.py
```

---

## Running the Master Test Suite

To run all 4 test suites sequentially:

```bash
python Test/run_all_tests.py
```

Expected output:

```
================================================================================
            LYRICA MASTER TEST SUITE — COMPLETE VERIFICATION
================================================================================

>>> Running: Genius HTML Depth-Tracking Parser Unit Tests (Test/test_genius_parser.py)
>>> Running: Real-World Live Genius Integration Tests (Test/test_real_genius.py)
>>> Running: Production Upgrades & Multi-Tier Verification (Test/test_production_upgrades.py)
>>> Running: High-Concurrency Performance & Stress Benchmark (Test/test_performance.py)

================================================================================
                             FINAL TEST REPORT
================================================================================
 [PASS] Genius HTML Depth-Tracking Parser Unit Tests            (0.24s)
 [PASS] Real-World Live Genius Integration Tests                (5.50s)
 [PASS] Production Upgrades & Multi-Tier Verification           (29.56s)
 [PASS] High-Concurrency Performance & Stress Benchmark         (1.81s)
--------------------------------------------------------------------------------
 Total Suite Execution Time: 37.12s
 [SUCCESS] ALL 4 TEST SUITES PASSED FLAWLESSLY!
================================================================================
```

---

## Running Individual Tests

### 1. Live Genius Integration Test
Tests live HTTP calls against Genius, validating that verses, choruses, and outros are completely extracted without leaked contributor badges or HTML noise:

```bash
python Test/test_real_genius.py
```

### 2. High-Concurrency Performance Benchmark
Stress tests the in-memory L1 cache and Flask REST API across concurrent thread pools:

```bash
python Test/test_performance.py
```

Benchmark output:

```
==========================================================================================
                         BENCHMARK RESULTS SUMMARY
==========================================================================================
Component / Route              |   Requests |       Throughput |         p50 |         p95 |         p99
------------------------------------------------------------------------------------------
L1 Memory LRU Cache            |      10,000 |    89,182 req/s |    0.000 ms |    0.001 ms |    0.001 ms
Flask API (GET /)              |       1,000 |     4,276 req/s |    0.189 ms |    0.361 ms |    3.010 ms
L1 Cache Hit Latency           |           1 |               — |    0.003 ms |           — |           —
==========================================================================================
```

### 3. Parser Unit Test
Tests parser depth-tracking against adversarial mock HTML:

```bash
python Test/test_genius_parser.py
```
