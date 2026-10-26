"""
Test/run_all_tests.py

Master test runner for the complete Lyrica test suite:
1. Unit tests: Genius HTML depth-tracking parser
2. Real-world integration tests: Genius live song extraction (The Weeknd, Queen)
3. Production upgrades test: Multi-tier caching, Redis, metadata, trending analytics
4. Performance & stress benchmark: L1 cache throughput (87k+ RPS) & Flask concurrency
"""

import sys
import subprocess
import time

TEST_FILES = [
    ("Genius HTML Depth-Tracking Parser Unit Tests", "Test/test_genius_parser.py"),
    ("Real-World Live Genius Integration Tests", "Test/test_real_genius.py"),
    ("Production Upgrades & Multi-Tier Verification", "Test/test_production_upgrades.py"),
    ("High-Concurrency Performance & Stress Benchmark", "Test/test_performance.py"),
]


def run_test_suite():
    print("=" * 80)
    print("            LYRICA MASTER TEST SUITE — COMPLETE VERIFICATION")
    print("=" * 80)

    results = []
    overall_start = time.perf_counter()

    for title, test_file in TEST_FILES:
        print(f"\n>>> Running: {title} ({test_file})")
        start = time.perf_counter()
        proc = subprocess.run([sys.executable, test_file], capture_output=False)
        duration = time.perf_counter() - start
        success = (proc.returncode == 0)
        results.append((title, success, duration))

    overall_duration = time.perf_counter() - overall_start

    print("\n" + "=" * 80)
    print("                             FINAL TEST REPORT")
    print("=" * 80)
    all_passed = True
    for title, success, duration in results:
        status_str = "[PASS]" if success else "[FAIL]"
        if not success:
            all_passed = False
        print(f" {status_str} {title:<55} ({duration:.2f}s)")

    print("-" * 80)
    print(f" Total Suite Execution Time: {overall_duration:.2f}s")
    if all_passed:
        print(" [SUCCESS] ALL 4 TEST SUITES PASSED FLAWLESSLY!")
    else:
        print(" [ERROR] SOME TESTS FAILED!")
    print("=" * 80)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    run_test_suite()
