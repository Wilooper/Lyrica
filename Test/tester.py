#!/usr/bin/env python3
"""
Lyrica API — Comprehensive Endpoint Tester & Debug Report Generator
====================================================================
Tests every endpoint on the live API and generates a self-contained
HTML debug report showing pass/fail status, response times, and
detailed diagnostics.

Usage:
    python lyrica_tester.py
    python lyrica_tester.py --base-url https://your-service.onrender.com
    python lyrica_tester.py --admin-key YOUR_KEY --output my_report.html

Requirements:
    pip install requests
"""

import argparse
import json
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Any

import requests

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_BASE_URL  = "https://test-0k.onrender.com"
DEFAULT_ADMIN_KEY = ""          # Set via --admin-key or edit here
REQUEST_TIMEOUT   = 60          # seconds per request (Render cold start can be slow)
REPORT_FILE       = "lyrica_debug_report.html"

# Test fixtures
TEST_ARTIST  = "karan aujla"
TEST_SONG    = "softly"
TEST_COUNTRY = "US"
TEST_JIOSAAVN_QUERY = "Kesariya"


# ─────────────────────────────────────────────────────────────────────────────
# RESULT TYPES
# ─────────────────────────────────────────────────────────────────────────────
class Status:
    PASS    = "PASS"
    FAIL    = "FAIL"
    WARN    = "WARN"
    SKIP    = "SKIP"


class TestResult:
    def __init__(
        self,
        name: str,
        endpoint: str,
        method: str,
        status: str,
        status_code: int | None,
        response_ms: float,
        checks: list[dict],
        response_body: Any = None,
        error: str | None = None,
    ):
        self.name         = name
        self.endpoint     = endpoint
        self.method       = method
        self.status       = status
        self.status_code  = status_code
        self.response_ms  = response_ms
        self.checks       = checks      # list of {"label": str, "ok": bool, "detail": str}
        self.response_body = response_body
        self.error        = error


# ─────────────────────────────────────────────────────────────────────────────
# CORE TEST RUNNER
# ─────────────────────────────────────────────────────────────────────────────
class LyricaTester:
    def __init__(self, base_url: str, admin_key: str = ""):
        self.base   = base_url.rstrip("/")
        self.admin  = admin_key
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        self.results: list[TestResult] = []

    # ── helpers ──────────────────────────────────────────────────────────────

    def _get(self, path: str, params: dict | None = None) -> tuple[requests.Response | None, float, str | None]:
        url = self.base + path
        t0  = time.monotonic()
        try:
            r = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            ms = (time.monotonic() - t0) * 1000
            return r, ms, None
        except requests.exceptions.ConnectionError as e:
            ms = (time.monotonic() - t0) * 1000
            return None, ms, f"Connection error: {e}"
        except requests.exceptions.Timeout:
            ms = (time.monotonic() - t0) * 1000
            return None, ms, f"Timeout after {REQUEST_TIMEOUT}s"
        except Exception as e:
            ms = (time.monotonic() - t0) * 1000
            return None, ms, f"Unexpected error: {e}"

    def _post(self, path: str, params: dict | None = None) -> tuple[requests.Response | None, float, str | None]:
        url = self.base + path
        t0  = time.monotonic()
        try:
            r = self.session.post(url, params=params, timeout=REQUEST_TIMEOUT)
            ms = (time.monotonic() - t0) * 1000
            return r, ms, None
        except requests.exceptions.ConnectionError as e:
            ms = (time.monotonic() - t0) * 1000
            return None, ms, f"Connection error: {e}"
        except requests.exceptions.Timeout:
            ms = (time.monotonic() - t0) * 1000
            return None, ms, f"Timeout after {REQUEST_TIMEOUT}s"
        except Exception as e:
            ms = (time.monotonic() - t0) * 1000
            return None, ms, f"Unexpected error: {e}"

    def _record(
        self,
        name: str,
        endpoint: str,
        method: str,
        r: requests.Response | None,
        ms: float,
        checks: list[dict],
        error: str | None,
    ) -> TestResult:
        passed  = all(c["ok"] for c in checks)
        warned  = any(c.get("warn") for c in checks if c["ok"])
        if error or r is None:
            overall = Status.FAIL
        elif not passed:
            overall = Status.FAIL
        elif warned:
            overall = Status.WARN
        else:
            overall = Status.PASS

        body = None
        if r is not None:
            try:
                body = r.json()
            except Exception:
                body = r.text[:500] if r.text else None

        result = TestResult(
            name         = name,
            endpoint     = endpoint,
            method       = method,
            status       = overall,
            status_code  = r.status_code if r else None,
            response_ms  = ms,
            checks       = checks,
            response_body = body,
            error        = error,
        )
        self.results.append(result)

        icon = "✅" if overall == Status.PASS else ("⚠️ " if overall == Status.WARN else "❌")
        print(f"  {icon} [{overall:4s}] {name} ({ms:.0f}ms)")
        return result

    # ── tests ─────────────────────────────────────────────────────────────────

    def test_health(self):
        print("\n── Core ────────────────────────────────────")
        r, ms, err = self._get("/")
        checks = []
        if r is not None:
            checks.append({"label": "HTTP 200", "ok": r.status_code == 200, "detail": f"Got {r.status_code}"})
            try:
                j = r.json()
                checks.append({"label": "Returns JSON", "ok": True, "detail": ""})
                checks.append({"label": "Has 'api' field", "ok": "api" in j, "detail": str(j.get("api"))})
                checks.append({"label": "Has 'version' field", "ok": "version" in j, "detail": str(j.get("version"))})
                checks.append({"label": "Has 'endpoints' field", "ok": "endpoints" in j, "detail": ""})
                checks.append({"label": "Status is 'active'", "ok": j.get("status") == "active", "detail": str(j.get("status"))})
            except Exception:
                checks.append({"label": "Returns JSON", "ok": False, "detail": "Body is not valid JSON"})
        else:
            checks.append({"label": "Reachable", "ok": False, "detail": err or "No response"})
        self._record("Health Check  GET /", "/", "GET", r, ms, checks, err)

    def test_favicon(self):
        r, ms, err = self._get("/favicon.ico")
        checks = []
        if r is not None:
            checks.append({"label": "HTTP 204", "ok": r.status_code == 204, "detail": f"Got {r.status_code}"})
        else:
            checks.append({"label": "Reachable", "ok": False, "detail": err})
        self._record("Favicon  GET /favicon.ico", "/favicon.ico", "GET", r, ms, checks, err)

    def test_404(self):
        r, ms, err = self._get("/this-endpoint-does-not-exist-xyz")
        checks = []
        if r is not None:
            checks.append({"label": "HTTP 404", "ok": r.status_code == 404, "detail": f"Got {r.status_code}"})
            try:
                j = r.json()
                checks.append({"label": "Returns JSON error body", "ok": "error" in j or "status" in j, "detail": ""})
            except Exception:
                checks.append({"label": "Returns JSON error body", "ok": False, "detail": "Not JSON"})
        else:
            checks.append({"label": "Reachable", "ok": False, "detail": err})
        self._record("404 Handler  GET /nonexistent", "/nonexistent", "GET", r, ms, checks, err)

    def test_lyrics_basic(self):
        print("\n── Lyrics ──────────────────────────────────")
        r, ms, err = self._get("/lyrics/", {"artist": TEST_ARTIST, "song": TEST_SONG})
        checks = []
        if r is not None:
            checks.append({"label": "HTTP 200", "ok": r.status_code == 200, "detail": f"Got {r.status_code}"})
            try:
                j = r.json()
                checks.append({"label": "status == success", "ok": j.get("status") == "success", "detail": str(j.get("status"))})
                data = j.get("data", {})
                has_lyrics = bool(data.get("lyrics") or data.get("plain_lyrics") or data.get("lyrics_text"))
                checks.append({"label": "Contains lyrics text", "ok": has_lyrics, "detail": "Found" if has_lyrics else "No lyrics key in data"})
                checks.append({"label": "Has 'source' field", "ok": bool(data.get("source")), "detail": str(data.get("source"))})
                checks.append({"label": "Has 'artist' field", "ok": bool(data.get("artist")), "detail": str(data.get("artist"))})
                checks.append({"label": "Has 'title' field", "ok": bool(data.get("title")), "detail": str(data.get("title"))})
                checks.append({"label": "Response < 15s (first request, Render cold start allowed)", "ok": ms < 15000, "detail": f"{ms:.0f}ms", "warn": ms > 8000})
            except Exception:
                checks.append({"label": "Returns JSON", "ok": False, "detail": "Not valid JSON"})
        else:
            checks.append({"label": "Reachable", "ok": False, "detail": err})
        self._record(f"Lyrics Basic  GET /lyrics/?artist={TEST_ARTIST}&song={TEST_SONG}", "/lyrics/", "GET", r, ms, checks, err)

    def test_lyrics_timestamps(self):
        r, ms, err = self._get("/lyrics/", {"artist": TEST_ARTIST, "song": TEST_SONG, "timestamps": "true"})
        checks = []
        if r is not None:
            checks.append({"label": "HTTP 200", "ok": r.status_code == 200, "detail": f"Got {r.status_code}"})
            try:
                j = r.json()
                checks.append({"label": "status == success", "ok": j.get("status") == "success", "detail": str(j.get("status"))})
                data = j.get("data", {})
                checks.append({"label": "hasTimestamps or timed_lyrics present", "ok": bool(data.get("hasTimestamps") or data.get("timed_lyrics")), "detail": f"hasTimestamps={data.get('hasTimestamps')}"})
            except Exception:
                checks.append({"label": "Returns JSON", "ok": False, "detail": "Not valid JSON"})
        else:
            checks.append({"label": "Reachable", "ok": False, "detail": err})
        self._record("Lyrics Timestamps  GET /lyrics/?timestamps=true", "/lyrics/", "GET", r, ms, checks, err)

    def test_lyrics_fast_mode(self):
        r, ms, err = self._get("/lyrics/", {"artist": TEST_ARTIST, "song": TEST_SONG, "fast": "true"})
        checks = []
        if r is not None:
            checks.append({"label": "HTTP 200", "ok": r.status_code == 200, "detail": f"Got {r.status_code}"})
            try:
                j = r.json()
                checks.append({"label": "status == success", "ok": j.get("status") == "success", "detail": str(j.get("status"))})
                checks.append({"label": "Fast mode < 8s", "ok": ms < 8000, "detail": f"{ms:.0f}ms"})
            except Exception:
                checks.append({"label": "Returns JSON", "ok": False, "detail": "Not valid JSON"})
        else:
            checks.append({"label": "Reachable", "ok": False, "detail": err})
        self._record("Lyrics Fast Mode  GET /lyrics/?fast=true", "/lyrics/", "GET", r, ms, checks, err)

    def test_lyrics_mood(self):
        r, ms, err = self._get("/lyrics/", {"artist": TEST_ARTIST, "song": TEST_SONG, "mood": "true"})
        checks = []
        if r is not None:
            checks.append({"label": "HTTP 200", "ok": r.status_code == 200, "detail": f"Got {r.status_code}"})
            try:
                j = r.json()
                checks.append({"label": "status == success", "ok": j.get("status") == "success", "detail": str(j.get("status"))})
                mood = j.get("mood_analysis", {})
                checks.append({"label": "mood_analysis present", "ok": bool(mood), "detail": str(mood)[:100]})
                checks.append({"label": "mood_analysis.sentiment present", "ok": "sentiment" in mood, "detail": str(mood.get("sentiment", {}))[:80]})
                sentiment = mood.get("sentiment", {})
                checks.append({"label": "polarity is a number", "ok": isinstance(sentiment.get("polarity"), (int, float)), "detail": str(sentiment.get("polarity"))})
            except Exception:
                checks.append({"label": "Returns JSON", "ok": False, "detail": "Not valid JSON"})
        else:
            checks.append({"label": "Reachable", "ok": False, "detail": err})
        self._record("Lyrics Mood Analysis  GET /lyrics/?mood=true", "/lyrics/", "GET", r, ms, checks, err)

    def test_lyrics_metadata(self):
        r, ms, err = self._get("/lyrics/", {"artist": TEST_ARTIST, "song": TEST_SONG, "metadata": "true"})
        checks = []
        if r is not None:
            checks.append({"label": "HTTP 200", "ok": r.status_code == 200, "detail": f"Got {r.status_code}"})
            try:
                j = r.json()
                checks.append({"label": "status == success", "ok": j.get("status") == "success", "detail": str(j.get("status"))})
                meta = j.get("metadata", {})
                checks.append({"label": "metadata block present", "ok": bool(meta), "detail": str(list(meta.keys()))[:80] if meta else "empty"})
                checks.append({"label": "metadata.title present", "ok": bool(meta.get("title")), "detail": str(meta.get("title"))})
                checks.append({"label": "metadata.album_art present", "ok": bool(meta.get("album_art")), "detail": str(meta.get("album_art", ""))[:60]})
            except Exception:
                checks.append({"label": "Returns JSON", "ok": False, "detail": "Not valid JSON"})
        else:
            checks.append({"label": "Reachable", "ok": False, "detail": err})
        self._record("Lyrics + Metadata  GET /lyrics/?metadata=true", "/lyrics/", "GET", r, ms, checks, err)

    def test_lyrics_all_params(self):
        r, ms, err = self._get("/lyrics/", {
            "artist": TEST_ARTIST, "song": TEST_SONG,
            "fast": "true", "timestamps": "true", "mood": "true", "metadata": "true"
        })
        checks = []
        if r is not None:
            checks.append({"label": "HTTP 200", "ok": r.status_code == 200, "detail": f"Got {r.status_code}"})
            try:
                j = r.json()
                checks.append({"label": "status == success", "ok": j.get("status") == "success", "detail": str(j.get("status"))})
                checks.append({"label": "mood_analysis present", "ok": "mood_analysis" in j, "detail": ""})
                checks.append({"label": "metadata present", "ok": "metadata" in j, "detail": ""})
            except Exception:
                checks.append({"label": "Returns JSON", "ok": False, "detail": "Not valid JSON"})
        else:
            checks.append({"label": "Reachable", "ok": False, "detail": err})
        self._record("Lyrics All Params  fast+timestamps+mood+metadata", "/lyrics/", "GET", r, ms, checks, err)

    def test_lyrics_missing_params(self):
        r, ms, err = self._get("/lyrics/", {})
        checks = []
        if r is not None:
            checks.append({"label": "HTTP 400", "ok": r.status_code == 400, "detail": f"Got {r.status_code}"})
            try:
                j = r.json()
                checks.append({"label": "Returns error body", "ok": j.get("status") == "error", "detail": str(j.get("error", {}).get("message", ""))[:80]})
            except Exception:
                checks.append({"label": "Returns JSON", "ok": False, "detail": "Not valid JSON"})
        else:
            checks.append({"label": "Reachable", "ok": False, "detail": err})
        self._record("Lyrics Missing Params  (expects 400)", "/lyrics/", "GET", r, ms, checks, err)

    def test_lyrics_custom_sequence(self):
        r, ms, err = self._get("/lyrics/", {
            "artist": TEST_ARTIST, "song": TEST_SONG, "pass": "true", "sequence": "2,3"
        })
        checks = []
        if r is not None:
            checks.append({"label": "HTTP 200 or 404", "ok": r.status_code in (200, 404), "detail": f"Got {r.status_code}"})
            try:
                j = r.json()
                checks.append({"label": "Returns valid JSON status", "ok": j.get("status") in ("success", "error"), "detail": str(j.get("status"))})
            except Exception:
                checks.append({"label": "Returns JSON", "ok": False, "detail": "Not valid JSON"})
        else:
            checks.append({"label": "Reachable", "ok": False, "detail": err})
        self._record("Lyrics Custom Sequence  pass=true&sequence=2,3", "/lyrics/", "GET", r, ms, checks, err)

    def test_lyrics_cache_hit(self):
        """Cache hit test: pre-warm with a request, then confirm the second is dramatically faster."""
        # Request 1 — may or may not hit cache (depends on prior tests)
        r1, ms1, _ = self._get("/lyrics/", {"artist": TEST_ARTIST, "song": TEST_SONG})
        # Request 2 — should always be a cache hit at this point
        r2, ms2, err = self._get("/lyrics/", {"artist": TEST_ARTIST, "song": TEST_SONG})
        checks = []
        if r2 is not None:
            checks.append({"label": "HTTP 200", "ok": r2.status_code == 200, "detail": f"Got {r2.status_code}"})
            # A cache hit should be at least 5× faster than the first (uncached) request
            # If ms1 < 1000 it was already cached — either way the 2nd must be < 1000ms
            cache_is_fast = ms2 < 1000
            checks.append({
                "label": "Cache hit is fast (<1000ms)",
                "ok": cache_is_fast,
                "detail": f"1st={ms1:.0f}ms  2nd={ms2:.0f}ms",
                "warn": ms2 > 400,
            })
            if ms1 > 1000:
                speedup = ms1 / ms2 if ms2 > 0 else 999
                checks.append({
                    "label": "Cache speedup ≥ 5×",
                    "ok": speedup >= 5,
                    "detail": f"{speedup:.1f}× faster",
                })
        else:
            checks.append({"label": "Reachable", "ok": False, "detail": err})
        self._record("Lyrics Cache Hit  (2nd request should be <1000ms)", "/lyrics/", "GET", r2, ms2, checks, err)

    def test_metadata(self):
        print("\n── Metadata ────────────────────────────────")
        r, ms, err = self._get("/metadata/", {"artist": TEST_ARTIST, "song": TEST_SONG})
        checks = []
        if r is not None:
            checks.append({"label": "HTTP 200", "ok": r.status_code == 200, "detail": f"Got {r.status_code}"})
            try:
                j = r.json()
                checks.append({"label": "status == success", "ok": j.get("status") == "success", "detail": str(j.get("status"))})
                meta = j.get("metadata", {})
                checks.append({"label": "metadata block present", "ok": bool(meta), "detail": str(list(meta.keys()))[:100]})
                checks.append({"label": "title present", "ok": bool(meta.get("title")), "detail": str(meta.get("title"))})
                checks.append({"label": "duration present", "ok": bool(meta.get("duration")), "detail": str(meta.get("duration", {}))[:60]})
                checks.append({"label": "sources listed", "ok": bool(j.get("sources")), "detail": str(j.get("sources"))})
            except Exception:
                checks.append({"label": "Returns JSON", "ok": False, "detail": "Not valid JSON"})
        else:
            checks.append({"label": "Reachable", "ok": False, "detail": err})
        self._record(f"Metadata  GET /metadata/?artist={TEST_ARTIST}&song={TEST_SONG}", "/metadata/", "GET", r, ms, checks, err)

    def test_metadata_missing(self):
        r, ms, err = self._get("/metadata/", {})
        checks = []
        if r is not None:
            checks.append({"label": "HTTP 400", "ok": r.status_code == 400, "detail": f"Got {r.status_code}"})
        else:
            checks.append({"label": "Reachable", "ok": False, "detail": err})
        self._record("Metadata Missing Params  (expects 400)", "/metadata/", "GET", r, ms, checks, err)

    def test_trending(self):
        print("\n── Trending ────────────────────────────────")
        r, ms, err = self._get("/trending/", {"country": TEST_COUNTRY, "limit": 5})
        checks = []
        if r is not None:
            checks.append({"label": "HTTP 200", "ok": r.status_code == 200, "detail": f"Got {r.status_code}"})
            try:
                j = r.json()
                checks.append({"label": "status == success", "ok": j.get("status") == "success", "detail": str(j.get("status"))})
                data = j.get("data", {})
                trending = data.get("trending", [])
                checks.append({"label": "trending list present", "ok": isinstance(trending, list), "detail": f"{len(trending)} songs"})
                checks.append({"label": "Has songs", "ok": len(trending) > 0, "detail": f"{len(trending)} songs returned"})
                if trending:
                    s = trending[0]
                    checks.append({"label": "Song has title", "ok": bool(s.get("title")), "detail": str(s.get("title"))})
                    checks.append({"label": "Song has artist", "ok": bool(s.get("artist")), "detail": str(s.get("artist"))})
                    checks.append({"label": "Song has rank", "ok": "rank" in s, "detail": str(s.get("rank"))})
            except Exception:
                checks.append({"label": "Returns JSON", "ok": False, "detail": "Not valid JSON"})
        else:
            checks.append({"label": "Reachable", "ok": False, "detail": err})
        self._record(f"Trending Single Country  GET /trending/?country={TEST_COUNTRY}", "/trending/", "GET", r, ms, checks, err)

    def test_trending_multi(self):
        r, ms, err = self._get("/trending/", {"countries": "US,GB,IN", "limit": 3})
        checks = []
        if r is not None:
            checks.append({"label": "HTTP 200", "ok": r.status_code == 200, "detail": f"Got {r.status_code}"})
            try:
                j = r.json()
                data = j.get("data", {})
                countries = data.get("countries", {})
                checks.append({"label": "Returns multiple countries", "ok": isinstance(countries, dict) and len(countries) >= 1, "detail": str(list(countries.keys()))})
            except Exception:
                checks.append({"label": "Returns JSON", "ok": False, "detail": "Not valid JSON"})
        else:
            checks.append({"label": "Reachable", "ok": False, "detail": err})
        self._record("Trending Multi-Country  GET /trending/?countries=US,GB,IN", "/trending/", "GET", r, ms, checks, err)

    def test_trending_invalid_country(self):
        r, ms, err = self._get("/trending/", {"country": "XX"})
        checks = []
        if r is not None:
            checks.append({"label": "HTTP 400", "ok": r.status_code == 400, "detail": f"Got {r.status_code}"})
            try:
                j = r.json()
                checks.append({"label": "Returns error with valid_countries hint", "ok": "valid_countries" in str(j), "detail": ""})
            except Exception:
                pass
        else:
            checks.append({"label": "Reachable", "ok": False, "detail": err})
        self._record("Trending Invalid Country  (expects 400)", "/trending/", "GET", r, ms, checks, err)

    def test_analytics_top_queries(self):
        print("\n── Analytics ───────────────────────────────")
        r, ms, err = self._get("/analytics/top-queries/", {"limit": 10})
        checks = []
        if r is not None:
            checks.append({"label": "HTTP 200", "ok": r.status_code == 200, "detail": f"Got {r.status_code}"})
            try:
                j = r.json()
                checks.append({"label": "status == success", "ok": j.get("status") == "success", "detail": str(j.get("status"))})
                data = j.get("data", {})
                checks.append({"label": "top_queries list present", "ok": "top_queries" in data, "detail": f"{len(data.get('top_queries', []))} queries"})
            except Exception:
                checks.append({"label": "Returns JSON", "ok": False, "detail": "Not valid JSON"})
        else:
            checks.append({"label": "Reachable", "ok": False, "detail": err})
        self._record("Analytics Top Queries  GET /analytics/top-queries/", "/analytics/top-queries/", "GET", r, ms, checks, err)

    def test_analytics_by_country(self):
        r, ms, err = self._get("/analytics/top-queries/", {"country": TEST_COUNTRY, "limit": 5})
        checks = []
        if r is not None:
            checks.append({"label": "HTTP 200", "ok": r.status_code == 200, "detail": f"Got {r.status_code}"})
            try:
                j = r.json()
                checks.append({"label": "status == success", "ok": j.get("status") == "success", "detail": str(j.get("status"))})
                data = j.get("data", {})
                checks.append({"label": "scope includes country", "ok": TEST_COUNTRY in str(data.get("scope", "")), "detail": str(data.get("scope"))})
            except Exception:
                checks.append({"label": "Returns JSON", "ok": False, "detail": "Not valid JSON"})
        else:
            checks.append({"label": "Reachable", "ok": False, "detail": err})
        self._record(f"Analytics Top Queries by Country  ?country={TEST_COUNTRY}", "/analytics/top-queries/", "GET", r, ms, checks, err)

    def test_analytics_trending_by_country(self):
        r, ms, err = self._get("/analytics/trending-by-country/", {"limit": 5})
        checks = []
        if r is not None:
            checks.append({"label": "HTTP 200", "ok": r.status_code == 200, "detail": f"Got {r.status_code}"})
            try:
                j = r.json()
                data = j.get("data", {})
                checks.append({"label": "countries dict present", "ok": "countries" in data, "detail": str(list(data.get("countries", {}).keys()))[:80]})
            except Exception:
                checks.append({"label": "Returns JSON", "ok": False, "detail": "Not valid JSON"})
        else:
            checks.append({"label": "Reachable", "ok": False, "detail": err})
        self._record("Analytics Trending by Country  GET /analytics/trending-by-country/", "/analytics/trending-by-country/", "GET", r, ms, checks, err)

    def test_analytics_trending_vs_queries(self):
        r, ms, err = self._get("/analytics/trending-vs-queries/", {"country": TEST_COUNTRY, "limit": 5})
        checks = []
        if r is not None:
            checks.append({"label": "HTTP 200", "ok": r.status_code == 200, "detail": f"Got {r.status_code}"})
            try:
                j = r.json()
                data = j.get("data", {})
                checks.append({"label": "trending_songs present", "ok": "trending_songs" in data, "detail": f"{len(data.get('trending_songs', []))} songs"})
                checks.append({"label": "top_user_queries present", "ok": "top_user_queries" in data, "detail": ""})
            except Exception:
                checks.append({"label": "Returns JSON", "ok": False, "detail": "Not valid JSON"})
        else:
            checks.append({"label": "Reachable", "ok": False, "detail": err})
        self._record(f"Analytics Trending vs Queries  ?country={TEST_COUNTRY}", "/analytics/trending-vs-queries/", "GET", r, ms, checks, err)

    def test_analytics_trending_intersection(self):
        r, ms, err = self._get("/analytics/trending-intersection/", {"country": TEST_COUNTRY, "limit": 5})
        checks = []
        if r is not None:
            checks.append({"label": "HTTP 200", "ok": r.status_code == 200, "detail": f"Got {r.status_code}"})
            try:
                j = r.json()
                checks.append({"label": "status == success", "ok": j.get("status") == "success", "detail": str(j.get("status"))})
                data = j.get("data", {})
                checks.append({"label": "matches list present", "ok": "matches" in data, "detail": f"{len(data.get('matches', []))} matches"})
            except Exception:
                checks.append({"label": "Returns JSON", "ok": False, "detail": "Not valid JSON"})
        else:
            checks.append({"label": "Reachable", "ok": False, "detail": err})
        self._record(f"Analytics Trending Intersection  ?country={TEST_COUNTRY}", "/analytics/trending-intersection/", "GET", r, ms, checks, err)

    def test_jiosaavn_search(self):
        print("\n── JioSaavn ────────────────────────────────")
        r, ms, err = self._get("/api/jiosaavn/search", {"q": TEST_JIOSAAVN_QUERY})
        checks = []
        if r is not None:
            checks.append({"label": "HTTP 200", "ok": r.status_code == 200, "detail": f"Got {r.status_code}"})
            try:
                j = r.json()
                checks.append({"label": "status == success", "ok": j.get("status") == "success", "detail": str(j.get("status"))})
                results = j.get("results", [])
                checks.append({"label": "results list present", "ok": isinstance(results, list), "detail": f"{len(results)} results"})
                checks.append({"label": "Has results", "ok": len(results) > 0, "detail": f"{len(results)} songs"})
                if results:
                    s = results[0]
                    checks.append({"label": "Song has title", "ok": bool(s.get("title")), "detail": str(s.get("title"))})
                    checks.append({"label": "Song has perma_url", "ok": bool(s.get("perma_url")), "detail": str(s.get("perma_url", ""))[:60]})
            except Exception:
                checks.append({"label": "Returns JSON", "ok": False, "detail": "Not valid JSON"})
        else:
            checks.append({"label": "Reachable", "ok": False, "detail": err})
        self._record(f"JioSaavn Search  GET /api/jiosaavn/search?q={TEST_JIOSAAVN_QUERY}", "/api/jiosaavn/search", "GET", r, ms, checks, err)

    def test_jiosaavn_search_missing(self):
        r, ms, err = self._get("/api/jiosaavn/search", {})
        checks = []
        if r is not None:
            checks.append({"label": "HTTP 400", "ok": r.status_code == 400, "detail": f"Got {r.status_code}"})
        else:
            checks.append({"label": "Reachable", "ok": False, "detail": err})
        self._record("JioSaavn Search Missing Query  (expects 400)", "/api/jiosaavn/search", "GET", r, ms, checks, err)

    def test_jiosaavn_play(self):
        """Get a perma_url from search first, then test play endpoint."""
        perma_url = None
        try:
            sr, _, _ = self._get("/api/jiosaavn/search", {"q": TEST_JIOSAAVN_QUERY})
            if sr and sr.status_code == 200:
                sj = sr.json()
                results = sj.get("results", [])
                if results:
                    perma_url = results[0].get("perma_url")
        except Exception:
            pass

        if not perma_url:
            self.results.append(TestResult(
                name="JioSaavn Play  GET /api/jiosaavn/play",
                endpoint="/api/jiosaavn/play",
                method="GET",
                status=Status.SKIP,
                status_code=None,
                response_ms=0,
                checks=[{"label": "Requires perma_url from search", "ok": False, "detail": "No perma_url obtained from search — skipping"}],
                error="Could not get perma_url from JioSaavn search",
            ))
            print(f"  ⏭️  [SKIP] JioSaavn Play  GET /api/jiosaavn/play")
            return

        r, ms, err = self._get("/api/jiosaavn/play", {"songLink": perma_url})
        checks = []
        if r is not None:
            checks.append({"label": "HTTP 200", "ok": r.status_code == 200, "detail": f"Got {r.status_code}"})
            try:
                j = r.json()
                checks.append({"label": "status == success", "ok": j.get("status") == "success", "detail": str(j.get("status"))})
                data = j.get("data", {})
                checks.append({"label": "stream_url present", "ok": bool(data.get("stream_url")), "detail": str(data.get("stream_url", ""))[:80]})
                checks.append({"label": "title present", "ok": bool(data.get("title")), "detail": str(data.get("title"))})
            except Exception:
                checks.append({"label": "Returns JSON", "ok": False, "detail": "Not valid JSON"})
        else:
            checks.append({"label": "Reachable", "ok": False, "detail": err})
        self._record("JioSaavn Play  GET /api/jiosaavn/play", "/api/jiosaavn/play", "GET", r, ms, checks, err)

    def test_jiosaavn_play_missing(self):
        r, ms, err = self._get("/api/jiosaavn/play", {})
        checks = []
        if r is not None:
            checks.append({"label": "HTTP 400", "ok": r.status_code == 400, "detail": f"Got {r.status_code}"})
        else:
            checks.append({"label": "Reachable", "ok": False, "detail": err})
        self._record("JioSaavn Play Missing Param  (expects 400)", "/api/jiosaavn/play", "GET", r, ms, checks, err)

    def test_cache_stats(self):
        print("\n── Cache & Admin ───────────────────────────")
        r, ms, err = self._get("/cache/stats")
        checks = []
        if r is not None:
            checks.append({"label": "HTTP 200", "ok": r.status_code == 200, "detail": f"Got {r.status_code}"})
            try:
                j = r.json()
                checks.append({"label": "status == success", "ok": j.get("status") == "success", "detail": str(j.get("status"))})
                checks.append({"label": "cache_files count present", "ok": "cache_files" in j, "detail": f"{j.get('cache_files')} files"})
                checks.append({"label": "ttl_seconds present", "ok": "ttl_seconds" in j, "detail": str(j.get("ttl_seconds")) + "s"})
            except Exception:
                checks.append({"label": "Returns JSON", "ok": False, "detail": "Not valid JSON"})
        else:
            checks.append({"label": "Reachable", "ok": False, "detail": err})
        self._record("Cache Stats  GET /cache/stats", "/cache/stats", "GET", r, ms, checks, err)

    def test_admin_cache_stats(self):
        if not self.admin:
            self.results.append(TestResult(
                name="Admin Cache Stats  GET /admin/cache/stats",
                endpoint="/admin/cache/stats",
                method="GET",
                status=Status.SKIP,
                status_code=None,
                response_ms=0,
                checks=[{"label": "ADMIN_KEY required", "ok": False, "detail": "Pass --admin-key to enable this test"}],
                error="No ADMIN_KEY provided",
            ))
            print("  ⏭️  [SKIP] Admin Cache Stats  (no --admin-key)")
            return

        r, ms, err = self._get("/admin/cache/stats", {"key": self.admin})
        checks = []
        if r is not None:
            checks.append({"label": "HTTP 200", "ok": r.status_code == 200, "detail": f"Got {r.status_code}"})
            try:
                j = r.json()
                checks.append({"label": "Has files list", "ok": "files" in j or "cache_files" in j, "detail": ""})
            except Exception:
                checks.append({"label": "Returns JSON", "ok": False, "detail": "Not valid JSON"})
        else:
            checks.append({"label": "Reachable", "ok": False, "detail": err})
        self._record("Admin Cache Stats  GET /admin/cache/stats", "/admin/cache/stats", "GET", r, ms, checks, err)

    def test_cache_clear_unauthorized(self):
        """Confirm /cache/clear rejects requests without admin key."""
        r, ms, err = self._post("/cache/clear")
        checks = []
        if r is not None:
            checks.append({"label": "Rejected without key (HTTP 403)", "ok": r.status_code == 403, "detail": f"Got {r.status_code} — should be 403"})
        else:
            checks.append({"label": "Reachable", "ok": False, "detail": err})
        self._record("Cache Clear Unauthorized  POST /cache/clear (expects 403)", "/cache/clear", "POST", r, ms, checks, err)

    def test_admin_unauthorized(self):
        """Confirm /admin/* rejects bad keys."""
        r, ms, err = self._get("/admin/cache/stats", {"key": "WRONG_KEY_xyz"})
        checks = []
        if r is not None:
            checks.append({"label": "Rejected with wrong key (HTTP 403)", "ok": r.status_code == 403, "detail": f"Got {r.status_code}"})
        else:
            checks.append({"label": "Reachable", "ok": False, "detail": err})
        self._record("Admin Route Wrong Key  GET /admin/cache/stats?key=WRONG (expects 403)", "/admin/cache/stats", "GET", r, ms, checks, err)

    def test_rate_limit_header(self):
        """Check that rate limit headers are present on responses."""
        r, ms, err = self._get("/lyrics/", {"artist": TEST_ARTIST, "song": TEST_SONG})
        checks = []
        if r is not None:
            checks.append({"label": "HTTP 200", "ok": r.status_code == 200, "detail": f"Got {r.status_code}"})
            rl_headers = {k: v for k, v in r.headers.items() if "ratelimit" in k.lower() or "x-ratelimit" in k.lower()}
            checks.append({"label": "Rate-limit headers present", "ok": len(rl_headers) > 0, "detail": str(rl_headers)[:120] if rl_headers else "None found"})
        else:
            checks.append({"label": "Reachable", "ok": False, "detail": err})
        self._record("Rate Limit Headers  present on /lyrics/ response", "/lyrics/", "GET", r, ms, checks, err)

    def test_gzip(self):
        """Check that gzip compression is active."""
        r, ms, err = self._get("/")
        checks = []
        if r is not None:
            enc = r.headers.get("Content-Encoding", "")
            # requests auto-decompresses; check if server sent gzip
            checks.append({"label": "HTTP 200", "ok": r.status_code == 200, "detail": f"Got {r.status_code}"})
            # Try requesting explicitly compressed
            try:
                r2 = self.session.get(
                    self.base + "/",
                    headers={"Accept-Encoding": "gzip"},
                    timeout=REQUEST_TIMEOUT,
                )
                enc2 = r2.raw.headers.get("Content-Encoding", "") or r2.headers.get("Content-Encoding", "")
                checks.append({"label": "Gzip compression active", "ok": "gzip" in enc2.lower(), "detail": f"Content-Encoding: {enc2 or 'not set'}"})
            except Exception as e:
                checks.append({"label": "Gzip check", "ok": False, "detail": str(e)})
        else:
            checks.append({"label": "Reachable", "ok": False, "detail": err})
        self._record("Gzip Compression  Content-Encoding: gzip on responses", "/", "GET", r, ms, checks, err)

    # ── run all ──────────────────────────────────────────────────────────────

    def run_all(self):
        print(f"\n{'='*60}")
        print(f"  LYRICA API TESTER")
        print(f"  Base URL : {self.base}")
        print(f"  Admin Key: {'set' if self.admin else 'not set'}")
        print(f"  Started  : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"{'='*60}")

        self.test_health()
        self.test_favicon()
        self.test_404()

        self.test_lyrics_basic()
        self.test_lyrics_timestamps()
        self.test_lyrics_fast_mode()
        self.test_lyrics_mood()
        self.test_lyrics_metadata()
        self.test_lyrics_all_params()
        self.test_lyrics_missing_params()
        self.test_lyrics_custom_sequence()
        self.test_lyrics_cache_hit()

        self.test_metadata()
        self.test_metadata_missing()

        self.test_trending()
        self.test_trending_multi()
        self.test_trending_invalid_country()

        self.test_analytics_top_queries()
        self.test_analytics_by_country()
        self.test_analytics_trending_by_country()
        self.test_analytics_trending_vs_queries()
        self.test_analytics_trending_intersection()

        self.test_jiosaavn_search()
        self.test_jiosaavn_search_missing()
        self.test_jiosaavn_play()
        self.test_jiosaavn_play_missing()

        self.test_cache_stats()
        self.test_admin_cache_stats()
        self.test_cache_clear_unauthorized()
        self.test_admin_unauthorized()
        self.test_rate_limit_header()
        self.test_gzip()

        total  = len(self.results)
        passed = sum(1 for r in self.results if r.status == Status.PASS)
        failed = sum(1 for r in self.results if r.status == Status.FAIL)
        warned = sum(1 for r in self.results if r.status == Status.WARN)
        skipped = sum(1 for r in self.results if r.status == Status.SKIP)

        print(f"\n{'='*60}")
        print(f"  RESULTS: {passed} passed  {failed} failed  {warned} warned  {skipped} skipped  / {total} total")
        print(f"{'='*60}\n")

        return self.results


# ─────────────────────────────────────────────────────────────────────────────
# HTML REPORT GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

def generate_html_report(results: list[TestResult], base_url: str, output_path: str):
    total   = len(results)
    passed  = sum(1 for r in results if r.status == Status.PASS)
    failed  = sum(1 for r in results if r.status == Status.FAIL)
    warned  = sum(1 for r in results if r.status == Status.WARN)
    skipped = sum(1 for r in results if r.status == Status.SKIP)
    health  = int((passed / max(total - skipped, 1)) * 100)

    avg_ms_list = [r.response_ms for r in results if r.status not in (Status.SKIP, Status.FAIL) or r.response_ms > 0]
    avg_ms = sum(avg_ms_list) / len(avg_ms_list) if avg_ms_list else 0

    # Colour for the big health arc
    arc_color = "#27ae60" if health >= 80 else ("#e67e22" if health >= 50 else "#e74c3c")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    def status_badge(s):
        colors = {
            Status.PASS: ("#27ae60", "✓ PASS"),
            Status.FAIL: ("#e74c3c", "✗ FAIL"),
            Status.WARN: ("#e67e22", "⚠ WARN"),
            Status.SKIP: ("#7f8c8d", "⏭ SKIP"),
        }
        bg, label = colors.get(s, ("#999", s))
        return f'<span class="badge" style="background:{bg}">{label}</span>'

    def check_row(c):
        icon = "✓" if c["ok"] else "✗"
        color = "#27ae60" if c["ok"] else "#e74c3c"
        detail = c.get("detail", "")
        return (
            f'<tr class="check-row">'
            f'<td style="color:{color};font-weight:700;width:28px">{icon}</td>'
            f'<td style="color:{color}">{c["label"]}</td>'
            f'<td class="detail-cell">{detail}</td>'
            f'</tr>'
        )

    rows_html = ""
    for i, r in enumerate(results):
        checks_html = "".join(check_row(c) for c in r.checks)
        body_preview = ""
        if r.response_body and r.status != Status.SKIP:
            try:
                pretty = json.dumps(r.response_body, indent=2, ensure_ascii=False)
                if len(pretty) > 1200:
                    pretty = pretty[:1200] + "\n... (truncated)"
                body_preview = f'<pre class="json-preview">{pretty}</pre>'
            except Exception:
                body_preview = f'<pre class="json-preview">{str(r.response_body)[:600]}</pre>'

        err_block = ""
        if r.error:
            err_block = f'<div class="error-block">⚠ {r.error}</div>'

        speed_class = ""
        if r.response_ms > 0:
            if r.response_ms < 300:
                speed_class = "speed-fast"
            elif r.response_ms < 2000:
                speed_class = "speed-ok"
            else:
                speed_class = "speed-slow"

        method_color = {"GET": "#2980b9", "POST": "#8e44ad"}.get(r.method, "#555")

        rows_html += f"""
        <div class="test-card {'card-fail' if r.status==Status.FAIL else ('card-warn' if r.status==Status.WARN else ('card-skip' if r.status==Status.SKIP else 'card-pass'))}" id="test-{i}">
          <div class="card-header" onclick="toggleCard({i})">
            <div class="card-left">
              {status_badge(r.status)}
              <span class="method-pill" style="background:{method_color}">{r.method}</span>
              <span class="test-name">{r.name}</span>
            </div>
            <div class="card-right">
              <span class="endpoint-label">{r.endpoint}</span>
              {'<span class="status-code">' + str(r.status_code) + '</span>' if r.status_code else ''}
              {'<span class="response-time ' + speed_class + '">' + f"{r.response_ms:.0f}ms" + '</span>' if r.response_ms > 0 else ''}
              <span class="chevron" id="chev-{i}">▼</span>
            </div>
          </div>
          <div class="card-body" id="body-{i}" style="display:none">
            {err_block}
            <table class="checks-table"><tbody>{checks_html}</tbody></table>
            {body_preview}
          </div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Lyrica API Debug Report</title>
  <style>
    :root {{
      --bg: #0f1117;
      --surface: #1a1d27;
      --surface2: #22263a;
      --border: #2e3352;
      --text: #e0e4f0;
      --muted: #7a82a0;
      --pass: #27ae60;
      --fail: #e74c3c;
      --warn: #e67e22;
      --skip: #7f8c8d;
      --blue: #4a9eba;
      --radius: 10px;
    }}
    * {{ box-sizing:border-box; margin:0; padding:0; }}
    body {{ background:var(--bg); color:var(--text); font-family:'Segoe UI',system-ui,sans-serif; font-size:14px; line-height:1.6; }}
    a {{ color:var(--blue); }}

    /* ── Header ── */
    .header {{ background:linear-gradient(135deg,#1b3a5c 0%,#0f1117 100%); padding:40px 40px 32px; border-bottom:2px solid var(--border); }}
    .header-row {{ display:flex; align-items:flex-start; justify-content:space-between; flex-wrap:wrap; gap:24px; }}
    .header h1 {{ font-size:2rem; font-weight:800; color:#fff; letter-spacing:-0.5px; }}
    .header .subtitle {{ color:var(--blue); font-size:0.95rem; margin-top:4px; }}
    .header .meta {{ color:var(--muted); font-size:0.82rem; margin-top:8px; }}

    /* ── Score ring ── */
    .score-ring {{ position:relative; width:110px; height:110px; flex-shrink:0; }}
    .score-ring svg {{ transform:rotate(-90deg); }}
    .score-ring .score-label {{ position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; }}
    .score-label .pct {{ font-size:1.6rem; font-weight:800; color:{arc_color}; }}
    .score-label .lbl {{ font-size:0.68rem; color:var(--muted); text-transform:uppercase; letter-spacing:1px; }}

    /* ── Stat bar ── */
    .stat-bar {{ display:flex; gap:12px; margin-top:28px; flex-wrap:wrap; }}
    .stat {{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:14px 20px; min-width:110px; text-align:center; }}
    .stat .val {{ font-size:1.9rem; font-weight:800; }}
    .stat .key {{ font-size:0.72rem; color:var(--muted); text-transform:uppercase; letter-spacing:1px; margin-top:2px; }}
    .stat.s-pass .val {{ color:var(--pass); }}
    .stat.s-fail .val {{ color:var(--fail); }}
    .stat.s-warn .val {{ color:var(--warn); }}
    .stat.s-skip .val {{ color:var(--skip); }}
    .stat.s-avg  .val {{ color:var(--blue); }}

    /* ── Filter bar ── */
    .filter-bar {{ padding:16px 40px; background:var(--surface); border-bottom:1px solid var(--border); display:flex; gap:10px; align-items:center; flex-wrap:wrap; }}
    .filter-bar label {{ color:var(--muted); font-size:0.82rem; margin-right:4px; }}
    .btn-filter {{ border:1px solid var(--border); background:var(--surface2); color:var(--text); border-radius:6px; padding:5px 14px; cursor:pointer; font-size:0.82rem; transition:all .15s; }}
    .btn-filter:hover {{ border-color:var(--blue); color:var(--blue); }}
    .btn-filter.active {{ background:var(--blue); color:#fff; border-color:var(--blue); }}
    .btn-all {{ background:var(--surface2); color:var(--text); border:1px solid var(--border); border-radius:6px; padding:5px 14px; cursor:pointer; font-size:0.82rem; margin-left:auto; }}
    .btn-all:hover {{ border-color:var(--blue); }}

    /* ── Search ── */
    .search-wrap {{ padding:14px 40px 0; }}
    .search-wrap input {{ width:100%; background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:9px 14px; color:var(--text); font-size:0.9rem; outline:none; transition:border .15s; }}
    .search-wrap input:focus {{ border-color:var(--blue); }}

    /* ── Cards ── */
    .cards {{ padding:20px 40px 60px; display:flex; flex-direction:column; gap:8px; }}
    .test-card {{ border-radius:var(--radius); border:1px solid var(--border); overflow:hidden; transition:box-shadow .15s; }}
    .test-card:hover {{ box-shadow:0 0 0 1px var(--blue); }}
    .card-pass {{ border-left:3px solid var(--pass); }}
    .card-fail {{ border-left:3px solid var(--fail); }}
    .card-warn {{ border-left:3px solid var(--warn); }}
    .card-skip {{ border-left:3px solid var(--skip); opacity:.7; }}

    .card-header {{ background:var(--surface); padding:13px 16px; display:flex; justify-content:space-between; align-items:center; cursor:pointer; gap:12px; flex-wrap:wrap; }}
    .card-header:hover {{ background:var(--surface2); }}
    .card-left {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; }}
    .card-right {{ display:flex; align-items:center; gap:10px; flex-shrink:0; flex-wrap:wrap; }}

    .badge {{ padding:2px 9px; border-radius:4px; font-size:0.72rem; font-weight:700; color:#fff; letter-spacing:.5px; }}
    .method-pill {{ padding:2px 8px; border-radius:4px; font-size:0.72rem; font-weight:700; color:#fff; }}
    .test-name {{ font-weight:600; font-size:0.88rem; }}
    .endpoint-label {{ font-family:monospace; font-size:0.78rem; color:var(--muted); }}
    .status-code {{ font-family:monospace; font-size:0.8rem; background:var(--surface2); padding:1px 7px; border-radius:4px; }}
    .response-time {{ font-family:monospace; font-size:0.8rem; padding:1px 7px; border-radius:4px; }}
    .speed-fast {{ background:#1a3d2b; color:#2ecc71; }}
    .speed-ok   {{ background:#3d2e1a; color:#e67e22; }}
    .speed-slow {{ background:#3d1a1a; color:#e74c3c; }}
    .chevron {{ color:var(--muted); font-size:0.75rem; transition:transform .2s; }}

    /* ── Card body ── */
    .card-body {{ background:var(--surface2); padding:16px; border-top:1px solid var(--border); }}
    .checks-table {{ width:100%; border-collapse:collapse; margin-bottom:12px; }}
    .check-row td {{ padding:4px 8px; font-size:0.83rem; }}
    .detail-cell {{ color:var(--muted); font-family:monospace; font-size:0.78rem; }}
    .error-block {{ background:#3d1a1a; border:1px solid #7d3030; border-radius:6px; padding:8px 12px; color:#e74c3c; font-size:0.83rem; margin-bottom:12px; }}
    .json-preview {{ background:#111420; border:1px solid var(--border); border-radius:6px; padding:12px; font-size:0.75rem; color:#a6e3a1; overflow:auto; max-height:280px; white-space:pre-wrap; word-break:break-all; }}

    /* ── Footer ── */
    .footer {{ text-align:center; padding:24px; color:var(--muted); font-size:0.78rem; border-top:1px solid var(--border); }}
  </style>
</head>
<body>

<div class="header">
  <div class="header-row">
    <div>
      <h1>🎵 Lyrica API Debug Report</h1>
      <div class="subtitle">Endpoint Health &amp; Regression Report</div>
      <div class="meta">
        Base URL: <strong><a href="{base_url}" target="_blank">{base_url}</a></strong> &nbsp;·&nbsp;
        Generated: <strong>{now}</strong> &nbsp;·&nbsp;
        {total} tests
      </div>
      <div class="stat-bar">
        <div class="stat s-pass"><div class="val">{passed}</div><div class="key">Passed</div></div>
        <div class="stat s-fail"><div class="val">{failed}</div><div class="key">Failed</div></div>
        <div class="stat s-warn"><div class="val">{warned}</div><div class="key">Warnings</div></div>
        <div class="stat s-skip"><div class="val">{skipped}</div><div class="key">Skipped</div></div>
        <div class="stat s-avg"><div class="val">{avg_ms:.0f}ms</div><div class="key">Avg resp.</div></div>
      </div>
    </div>
    <div class="score-ring">
      <svg width="110" height="110" viewBox="0 0 110 110">
        <circle cx="55" cy="55" r="46" fill="none" stroke="#2e3352" stroke-width="10"/>
        <circle cx="55" cy="55" r="46" fill="none" stroke="{arc_color}" stroke-width="10"
          stroke-dasharray="{2*3.14159*46}"
          stroke-dashoffset="{2*3.14159*46*(1 - health/100)}"
          stroke-linecap="round"/>
      </svg>
      <div class="score-label">
        <span class="pct">{health}%</span>
        <span class="lbl">Health</span>
      </div>
    </div>
  </div>
</div>

<div class="filter-bar">
  <label>Filter:</label>
  <button class="btn-filter active" onclick="filterCards('ALL')" id="f-ALL">All ({total})</button>
  <button class="btn-filter" onclick="filterCards('PASS')" id="f-PASS">✓ Pass ({passed})</button>
  <button class="btn-filter" onclick="filterCards('FAIL')" id="f-FAIL">✗ Fail ({failed})</button>
  <button class="btn-filter" onclick="filterCards('WARN')" id="f-WARN">⚠ Warn ({warned})</button>
  <button class="btn-filter" onclick="filterCards('SKIP')" id="f-SKIP">⏭ Skip ({skipped})</button>
  <button class="btn-all" onclick="expandAll()">Expand All</button>
  <button class="btn-all" onclick="collapseAll()">Collapse All</button>
</div>

<div class="search-wrap">
  <input type="text" placeholder="Search tests by name or endpoint…" oninput="searchCards(this.value)" id="searchInput"/>
</div>

<div class="cards" id="cards-container">
{rows_html}
</div>

<div class="footer">
  Lyrica API Debug Report &nbsp;·&nbsp; {now} &nbsp;·&nbsp; {total} tests &nbsp;·&nbsp;
  <strong style="color:{arc_color}">{health}% healthy</strong>
</div>

<script>
  function toggleCard(i) {{
    const body = document.getElementById('body-' + i);
    const chev = document.getElementById('chev-' + i);
    const open = body.style.display !== 'none';
    body.style.display = open ? 'none' : 'block';
    chev.style.transform = open ? '' : 'rotate(180deg)';
  }}
  function expandAll() {{
    document.querySelectorAll('.card-body').forEach((b,i) => {{
      b.style.display = 'block';
      const c = document.getElementById('chev-' + i);
      if(c) c.style.transform = 'rotate(180deg)';
    }});
  }}
  function collapseAll() {{
    document.querySelectorAll('.card-body').forEach((b,i) => {{
      b.style.display = 'none';
      const c = document.getElementById('chev-' + i);
      if(c) c.style.transform = '';
    }});
  }}
  let currentFilter = 'ALL';
  function filterCards(f) {{
    currentFilter = f;
    document.querySelectorAll('.btn-filter').forEach(b => b.classList.remove('active'));
    document.getElementById('f-' + f).classList.add('active');
    applyFilters();
  }}
  function searchCards(q) {{ applyFilters(q); }}
  function applyFilters(q) {{
    q = (q || document.getElementById('searchInput').value || '').toLowerCase();
    document.querySelectorAll('.test-card').forEach(card => {{
      const text = card.innerText.toLowerCase();
      const matchSearch = !q || text.includes(q);
      const classMap = {{'PASS':'card-pass','FAIL':'card-fail','WARN':'card-warn','SKIP':'card-skip'}};
      const matchFilter = currentFilter === 'ALL' || card.classList.contains(classMap[currentFilter]);
      card.style.display = (matchSearch && matchFilter) ? '' : 'none';
    }});
  }}
  // Auto-expand failed tests
  document.querySelectorAll('.card-fail').forEach(card => {{
    const id = card.id.replace('test-', '');
    const body = document.getElementById('body-' + id);
    const chev = document.getElementById('chev-' + id);
    if(body) body.style.display = 'block';
    if(chev) chev.style.transform = 'rotate(180deg)';
  }});
</script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"📄 Report saved → {output_path}")


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Lyrica API endpoint tester")
    parser.add_argument("--base-url",  default=DEFAULT_BASE_URL,  help="API base URL")
    parser.add_argument("--admin-key", default=DEFAULT_ADMIN_KEY, help="Admin key for protected endpoints")
    parser.add_argument("--output",    default=REPORT_FILE,        help="Output HTML report filename")
    args = parser.parse_args()

    tester  = LyricaTester(base_url=args.base_url, admin_key=args.admin_key)
    results = tester.run_all()
    generate_html_report(results, args.base_url, args.output)


if __name__ == "__main__":
    main()
