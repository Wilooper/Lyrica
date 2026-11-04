"""Tests for the Lyrica v2 correctness and performance core.

No network access is required: fake fetchers are injected into the registry.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time

import pytest

os.environ.setdefault("RATELIMIT_ENABLED", "false")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("ADMIN_KEY", "test-admin-key")

from src.app import create_app  # noqa: E402
from src.cache import (  # noqa: E402
    make_lyrics_cache_key,
    make_view_cache_key,
    save_raw,
    load_raw,
    clear_cache,
)
from src.core import providers  # noqa: E402
from src.core.negative_cache import negative_cache  # noqa: E402
from src.core.normalizer import normalize_identity  # noqa: E402
from src.core.singleflight import singleflight  # noqa: E402
from src.core.tiers import derive_view, detect_tier, to_lean  # noqa: E402
from src.core.verifier import verify_result  # noqa: E402
from src.sources import ALL_FETCHERS  # noqa: E402
from src.sources.base_fetcher import parse_lrc  # noqa: E402
from src.sources.lrclib_fetcher import LRCLIBFetcher  # noqa: E402


class _FakeFetcher:
    def __init__(self, result=None, delay: float = 0.0):
        self.result = result
        self.delay = delay
        self.calls = 0

    async def fetch(self, artist, song, timestamps=False, **kwargs):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.result


@pytest.fixture()
def client():
    app = create_app()
    app.config["TESTING"] = True
    app.config["RATELIMIT_ENABLED"] = False
    return app.test_client()


@pytest.fixture()
def registry(monkeypatch):
    """Replace the provider registry with a single fake fetcher."""
    import src.fetch_controller as fetch_controller

    saved = dict(ALL_FETCHERS)
    ALL_FETCHERS.clear()
    monkeypatch.setattr(fetch_controller, "_SOURCE_ORDER", ["fake"])
    providers.reset()
    negative_cache.clear()
    try:
        yield ALL_FETCHERS
    finally:
        ALL_FETCHERS.clear()
        ALL_FETCHERS.update(saved)
        providers.reset()
        negative_cache.clear()


def _line_result(artist="Test Artist", title="Test Song"):
    return {
        "source": "fake",
        "artist": artist,
        "title": title,
        "lyrics": "line one\nline two",
        "hasTimestamps": True,
        "duration": 30,
        "timed_lyrics": [
            {"id": "lrc_0", "text": "line one", "start_time": 1000, "end_time": 5000},
            {"id": "lrc_1", "text": "line two", "start_time": 5000, "end_time": 9000},
        ],
    }


def _word_result():
    return {
        "source": "fake",
        "artist": "Test Artist",
        "title": "Test Song",
        "lyrics": "line one",
        "hasTimestamps": True,
        "sync_level": "syllable",
        "timed_lyrics": [{
            "id": "lrc_0",
            "text": "line one",
            "start_time": 1000,
            "end_time": 3000,
            "words": [{
                "text": "line",
                "start": 1000,
                "end": 2000,
                "syllables": [
                    {"text": "li", "start": 1000, "end": 1500},
                    {"text": "ne", "start": 1500, "end": 2000},
                ],
            }],
        }],
    }


# ── Normalizer / verifier ────────────────────────────────────────────────────

def test_normalizer_collapses_edition_noise():
    assert normalize_identity("The  Beatles", "Hey Jude (Remastered)") == ("the beatles", "hey jude")
    assert normalize_identity("Daft Punk", "Get Lucky (feat. Pharrell Williams)") == ("daft punk", "get lucky")
    assert normalize_identity("ARTIST", "Song - Live")[1] == "song"
    assert normalize_identity("ARTIST", "Song (Official Video)")[1] == "song"
    assert normalize_identity("ARTIST", "Song - Official Music Video")[1] == "song"
    assert normalize_identity("ARTIST", "Song - 2011 Remaster")[1] == "song"
    # Legitimate titles that merely contain a noise keyword must survive.
    assert normalize_identity("Artist", "Live Forever") == ("artist", "live forever")
    assert normalize_identity("Artist", "I Live") == ("artist", "i live")


def test_verifier_rejects_wrong_song():
    verdict = verify_result(
        "Talwiinder",
        "Nasha",
        {"artist": "Ed Sheeran", "title": "Shape of You", "lyrics": "The club isn't the best place"},
    )
    assert verdict["accepted"] is False
    assert verdict["confidence"] < 0.6


def test_verifier_accepts_correct_result():
    verdict = verify_result("Coldplay", "Yellow", _line_result("Coldplay", "Yellow"))
    assert verdict["accepted"] is True
    assert verdict["confidence"] >= 0.85


def test_verifier_rejects_boilerplate_and_html():
    boilerplate = {"artist": "A", "title": "T", "lyrics": "Lyrics not available"}
    html = {"artist": "A", "title": "T", "lyrics": "<html><body>502</body></html>"}
    assert verify_result("A", "T", boilerplate)["accepted"] is False
    assert verify_result("A", "T", html)["accepted"] is False


# ── LRC parsing / tiers / lean payload ───────────────────────────────────────

def test_parse_lrc_multiple_tags_offset_and_sorting():
    lrc = "[ar:Artist]\n[offset:500]\n[00:01.00][00:10.50]Chorus\n[00:05.2]Verse"
    parsed = parse_lrc(lrc)
    assert [entry["start_time"] for entry in parsed] == [1500, 5700, 11000]
    assert parsed[0]["end_time"] == 5700
    assert parsed[-1]["end_time"] == 15000  # last line start + 4s


def test_tier_derivation_never_upgrades():
    word = {"status": "success", "data": _word_result()}
    assert detect_tier(word) == "syllable"

    line = derive_view(word, "line")
    assert "words" not in line["data"]["timed_lyrics"][0]

    plain = derive_view(word, "plain")
    assert plain["data"]["hasTimestamps"] is False
    assert "timed_lyrics" not in plain["data"]
    assert plain["data"]["lyrics"]

    # A plain entry can never be turned into timed lines.
    plain_raw = {"status": "success", "data": {"source": "x", "lyrics": "a\nb"}}
    assert "timed_lyrics" not in derive_view(plain_raw, "line")["data"]


def test_lean_payload_is_small_and_compact():
    lines = []
    for i in range(60):
        lines.append({
            "id": f"lrc_{i}",
            "text": f"lyric line number {i}",
            "start_time": i * 3000,
            "end_time": (i + 1) * 3000,
        })
    result = {"status": "success", "data": {
        "source": "fake", "artist": "A", "title": "T", "duration": 180,
        "hasTimestamps": True, "timed_lyrics": lines,
    }}
    lean = to_lean(result, "line")
    assert lean["lines"][0] == [0, "lyric line number 0"]
    assert "id" not in lean["lines"][0]
    assert len(lean["lines"]) == 60
    assert len(json.dumps(lean)) < 5000


def test_lean_word_and_syllable_nesting():
    lean = to_lean({"status": "success", "data": _word_result()}, "syllable")
    start, text, words = lean["lines"][0]
    assert (start, text) == (1000, "line one")
    assert words[0][1] == "line"
    assert words[0][2][0][1] == "li"


# ── Singleflight / cache key ─────────────────────────────────────────────────

def test_singleflight_runs_leader_once():
    calls = 0
    lock = threading.Lock()

    def worker():
        nonlocal calls
        with singleflight.run("singleflight-test", timeout=5) as leader:
            if leader:
                with lock:
                    calls += 1
                time.sleep(0.1)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert calls == 1


def test_raw_cache_key_ignores_view_flags():
    a = make_lyrics_cache_key("The  Beatles", "Hey Jude", sequence=None)
    b = make_lyrics_cache_key("the beatles", "hey jude", sequence=None)
    assert a == b
    # The rendered view key must still distinguish flags.
    v1 = make_view_cache_key("The Beatles", "Hey Jude", timestamps=True)
    v2 = make_view_cache_key("The Beatles", "Hey Jude", timestamps=False)
    assert v1 != v2


# ── Provider safety ──────────────────────────────────────────────────────────

def test_breaker_opens_and_recovers_after_probes():
    providers.reset()
    state = providers.get_state("breaker-test")
    for _ in range(5):
        state.record_failure("boom")
    assert state.snapshot()["state"] == "open"

    allowed, reason = state.try_acquire()
    assert allowed is False and reason == "breaker_open"

    state.opened_at -= 3600  # simulate cooldown expiry
    allowed, _ = state.try_acquire()
    assert allowed is True  # half-open probe

    state.record_success(0.05)
    state.record_success(0.05)
    assert state.snapshot()["state"] == "closed"


def test_rejected_and_cancelled_probes_do_not_wedge_breaker():
    providers.reset()
    state = providers.get_state("probe-test")
    for _ in range(5):
        state.record_failure("boom")
    state.opened_at -= 3600

    assert state.try_acquire()[0] is True  # half-open probe
    state.record_rejected("wrong_song")
    assert state.try_acquire()[0] is True  # probe slot was released

    state.record_aborted()  # e.g. fast-mode task cancellation
    assert state.try_acquire()[0] is True


def test_youtube_and_token_gated_providers_are_not_loaded():
    if "youtube" in ALL_FETCHERS:
        pytest.fail("YouTube fetcher should be disabled until it is rebuilt")
    if not os.getenv("MUSIXMATCH_TOKEN"):
        assert "musixmatch" not in ALL_FETCHERS
    if not (os.getenv("APPLE_MUSIC_DEVELOPER_TOKEN") or os.getenv("DEVELOPER_TOKEN")):
        assert "apple_music" not in ALL_FETCHERS


def test_word_sync_restricted_to_word_capable_providers(registry, monkeypatch):
    import src.fetch_controller as fetch_controller

    registry["lrcmux"] = _FakeFetcher(None)
    registry["lrclib"] = _FakeFetcher(None)
    registry["genius"] = _FakeFetcher(None)
    monkeypatch.setattr(
        fetch_controller, "_SOURCE_ORDER", ["lrclib", "lrcmux", "genius"]
    )

    seen: list[list[str]] = []

    async def fake_try_phase(phase, *args, **kwargs):
        seen.append(list(phase["sources"]))
        return None

    monkeypatch.setattr(fetch_controller, "_try_phase", fake_try_phase)
    asyncio.run(
        fetch_controller.fetch_lyrics_controller(
            "WordArtist", "WordSong", timestamps=True, word_level=True
        )
    )

    assert seen
    assert all(set(sources) <= {"lrcmux", "apple_music"} for sources in seen)


def test_provider_errors_are_redacted():
    providers.reset()
    state = providers.get_state("redact-test")
    state.record_failure("GET https://api.example/x?access_token=super-secret failed")
    last_error = state.snapshot()["last_error"]
    assert "super-secret" not in last_error
    assert "<redacted>" in last_error

    assert "abc123" not in providers.redact("Authorization: Bearer abc123")


def test_quota_bucket_stops_at_limit(monkeypatch):
    monkeypatch.setenv("LYRICA_PROVIDER_QUOTATEST_RPM", "1")
    providers.reset()
    state = providers.get_state("quotatest")
    assert state.try_acquire()[0] is True
    allowed, reason = state.try_acquire()
    assert allowed is False and reason == "quota_exhausted"


# ── End-to-end routes with a fake provider ───────────────────────────────────

def test_missing_song_is_negative_cached(client, registry):
    fake = _FakeFetcher(None)
    registry["fake"] = fake

    url = "/lyrics/?artist=NegCacheArtist&song=Missing&sequence=fake"
    first = client.get(url)
    assert first.status_code == 200
    assert first.get_json()["status"] == "error"
    assert fake.calls == 1

    second = client.get(url)
    assert second.status_code == 200
    assert fake.calls == 1  # zero upstream calls on the second request


def test_concurrent_missing_song_gets_consistent_not_found(client, registry):
    fake = _FakeFetcher(None, delay=0.2)
    registry["fake"] = fake
    url = "/v2/lyrics?artist=ConcurrentMissing&song=Nothing"
    codes: list[int] = []
    lock = threading.Lock()

    def worker():
        response = client.application.test_client().get(url)
        with lock:
            codes.append(response.status_code)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert fake.calls == 1
    assert codes == [404] * 20


def test_wrong_song_result_is_rejected_and_not_cached(client, registry):
    wrong = _FakeFetcher({
        "source": "fake",
        "artist": "Someone Else",
        "title": "A Different Song",
        "lyrics": "completely unrelated words here",
        "hasTimestamps": False,
    })
    registry["fake"] = wrong

    artist, song = "WrongSongArtist", "Wanted Song"
    response = client.get(f"/lyrics/?artist={artist}&song={song}&sequence=fake")
    assert response.get_json()["status"] == "error"
    assert wrong.calls == 1
    assert load_raw(make_lyrics_cache_key(artist, song, "fake")) is None


def test_one_raw_fetch_serves_plain_and_line_views(client, registry):
    fake = _FakeFetcher(_line_result("CacheArtist", "CacheSong"))
    registry["fake"] = fake

    base = "/lyrics/?artist=CacheArtist&song=CacheSong&sequence=fake"
    timed = client.get(base + "&timestamps=true")
    assert timed.get_json()["data"]["hasTimestamps"] is True
    assert fake.calls == 1

    plain = client.get(base)
    data = plain.get_json()["data"]
    assert data["hasTimestamps"] is False
    assert "timed_lyrics" not in data
    assert data["lyrics"] == "line one\nline two"
    assert fake.calls == 1  # the raw entry was derived, not refetched


def test_100_concurrent_identical_requests_fetch_once(client, registry):
    fake = _FakeFetcher(_line_result("StampedeArtist", "StampedeSong"), delay=0.2)
    registry["fake"] = fake
    url = "/lyrics/?artist=StampedeArtist&song=StampedeSong&sequence=fake&timestamps=true"
    statuses: list[int] = []
    lock = threading.Lock()

    def worker():
        local_client = client.application.test_client()
        response = local_client.get(url)
        with lock:
            statuses.append(response.status_code)

    threads = [threading.Thread(target=worker) for _ in range(100)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert fake.calls == 1
    assert statuses == [200] * 100


def test_lower_tier_upgrade_does_not_overwrite_richer_cache(client, registry):
    artist, song = "MonotonicArtist", "MonotonicSong"
    key = make_lyrics_cache_key(artist, song)
    save_raw(key, {"status": "success", "data": _line_result(artist, song)}, "line")

    # A word request is routed to lrcmux, which only returns plain text here.
    plain = {
        "source": "fake",
        "artist": artist,
        "title": song,
        "lyrics": "plain only lyrics that are long enough",
        "hasTimestamps": False,
    }
    registry["lrcmux"] = _FakeFetcher(plain)

    response = client.get(
        f"/v2/lyrics?artist={artist}&song={song}&tier=word"
    )
    assert response.status_code == 200
    assert response.get_json()["tier"] == "line"
    cached = load_raw(key)
    assert cached is not None and cached[1] == "line"


def test_v1_view_cache_etag_and_304(client, registry):
    fake = _FakeFetcher(_line_result("EtagArtist", "EtagSong"))
    registry["fake"] = fake
    url = "/lyrics/?artist=EtagArtist&song=EtagSong&sequence=fake&timestamps=true"

    first = client.get(url)
    assert first.status_code == 200
    assert first.headers["ETag"]
    second = client.get(url)
    assert second.headers.get("X-Cache") == "HIT"
    assert second.get_json() == first.get_json()

    cached = client.get(url, headers={"If-None-Match": first.headers["ETag"]})
    assert cached.status_code == 304


def test_v2_lean_payload_and_tier_guard(client, registry):
    artist, song = "V2Artist", "V2Song"
    result = {"status": "success", "data": _line_result(artist, song)}
    save_raw(make_lyrics_cache_key(artist, song), result, "line")

    response = client.get(f"/v2/lyrics?artist={artist}&song={song}&tier=line")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["v"] == 2
    assert payload["tier"] == "line"
    assert payload["lines"][0] == [1000, "line one"]
    assert "timed_lyrics" not in payload
    assert response.headers["ETag"]

    not_modified = client.get(
        f"/v2/lyrics?artist={artist}&song={song}&tier=line",
        headers={"If-None-Match": response.headers["ETag"]},
    )
    assert not_modified.status_code == 304

    # A plain-only cached entry cannot satisfy a word request unless allowed.
    plain_artist, plain_song = "V2PlainArtist", "V2PlainSong"
    plain = {"status": "success", "data": {
        "source": "fake", "artist": plain_artist, "title": plain_song, "lyrics": "a\nb",
    }}
    save_raw(make_lyrics_cache_key(plain_artist, plain_song), plain, "plain")
    registry["fake"] = _FakeFetcher(None)
    blocked = client.get(
        f"/v2/lyrics?artist={plain_artist}&song={plain_song}&tier=word&allow_lower=false"
    )
    assert blocked.status_code == 404
    assert blocked.get_json()["err"] == "tier_unavailable"

    # The failed upgrade is remembered briefly; no repeated upstream call.
    client.get(
        f"/v2/lyrics?artist={plain_artist}&song={plain_song}&tier=word&allow_lower=false"
    )
    assert registry["fake"].calls == 1


def test_lrclib_plain_request_strips_timestamps():
    """A plain request (timestamps=False) with only syncedLyrics must strip tags."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    fetcher = LRCLIBFetcher()
    synced = "[00:01.00]Hello world\n[00:05.00]Second line"
    mock_data = {
        "artistName": "Test",
        "trackName": "Song",
        "duration": 30,
        "syncedLyrics": synced,
        "plainLyrics": None,
        "instrumental": False,
    }

    async def fake_get(client, params):
        return mock_data

    fetcher._get = fake_get
    fetcher._search = AsyncMock(return_value=[])

    result = asyncio.run(fetcher._fetch_with_client(MagicMock(), "Test", "Song", timestamps=False))
    assert result is not None
    assert result["hasTimestamps"] is False
    assert "timed_lyrics" not in result
    assert result["lyrics"] == "Hello world\nSecond line"


def test_compression_is_off_by_default(client):
    response = client.get("/", headers={"Accept-Encoding": "gzip"})
    assert "Content-Encoding" not in response.headers


def test_clear_cache_clears_negative_entries():
    negative_cache.set("some-key", "not_found")
    assert negative_cache.get("some-key") is not None
    result = clear_cache()
    assert negative_cache.get("some-key") is None
    assert "negative_items_cleared" in result
