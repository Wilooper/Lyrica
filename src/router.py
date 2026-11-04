from flask import jsonify, request, render_template, Response, current_app
from datetime import datetime, timezone
import os
import re
import hmac
import hashlib
import asyncio
import atexit
import threading
import weakref
import httpx as _httpx

from src.proxy_manager import get_proxy_manager
from src.user_config import get_user_config, reload_user_config

from src.logger import get_logger
from src.cache import (
    make_lyrics_cache_key,
    make_view_cache_key,
    load_raw,
    save_raw,
    load_view,
    save_view,
    clear_cache,
    cache_stats,
)
from src.core import providers
from src.core.negative_cache import negative_cache
from src.core.singleflight import singleflight
from src.core.tiers import (
    TIERS,
    derive_view,
    detect_tier,
    normalize_tier,
    requested_tier,
    tier_rank,
    to_lean,
)
from src.fetch_controller import fetch_lyrics_controller
from src.sentiment_analyzer import analyze_sentiment, analyze_word_frequency, extract_lyrics_text
from src.metadata_extractor import enhance_lyrics_with_metadata, get_metadata_only
from src.sources import ALL_FETCHERS
from src.sources.jiosaavan_fetcher import search_jiosaavn, get_jiosaavn_stream
from src.trending_analytics import TrendingAnalyticsEngine, Country
from src import __version__
from src.config import ADMIN_KEY, GROQ_MODEL
from src.groq_processor import process_lyrics
from src.groq_key_manager import get_key_manager
from src.translation_cache import (
    make_translation_cache_key,
    load_translation_cache,
    save_translation_cache,
)

logger = get_logger("router")

# Initialize Trending Analytics Engine (global instance)
trending_engine = TrendingAnalyticsEngine(cache_ttl_hours=24)

_IS_PRODUCTION = os.getenv("LYRICA_ENV", "").lower() == "production"
_MAX_TEXT_LEN = int(os.getenv("MAX_TEXT_LENGTH", "200"))
_thread_state = threading.local()
_LOOPS: "weakref.WeakSet[asyncio.AbstractEventLoop]" = weakref.WeakSet()


@atexit.register
def _close_thread_loops() -> None:
    """Close per-thread loops before interpreter teardown.

    Python otherwise destroys the selector's file descriptors first and then
    garbage-collects the loop, which emits a noisy "Invalid file descriptor: -1"
    warning on shutdown.
    """
    for loop in list(_LOOPS):
        if loop.is_closed() or loop.is_running():
            continue
        try:
            loop.close()
        except Exception:  # pragma: no cover - best effort during shutdown
            pass

# Shared blocking client for the one legacy sync endpoint (/suggestion).
# httpx.Client is thread-safe; reuse avoids a TCP/TLS handshake per request.
_SUGGESTION_CLIENT = _httpx.Client(
    timeout=_httpx.Timeout(connect=3.0, read=7.0, write=3.0, pool=2.0),
    headers={"User-Agent": "Lyrica/1.5.0 (https://github.com/Wilooper/Lyrica)"},
    follow_redirects=True,
)


def _error_details(exc: BaseException) -> dict:
    """Only expose raw exception text outside production.

    Upstream exception messages can contain internal hostnames, tokens, or
    filesystem paths. Clients still get the stable error envelope.
    """
    if _IS_PRODUCTION:
        return {}
    return {"details": str(exc)}


def _admin_key_ok(key: str | None) -> bool:
    """Constant-time admin key comparison."""
    if not ADMIN_KEY or not key:
        return False
    return hmac.compare_digest(str(key), str(ADMIN_KEY))


def _sanitize_text(value: str, max_len: int = _MAX_TEXT_LEN) -> str:
    """Strip control characters and bound user-controlled text fields."""
    value = re.sub(r"[\x00-\x1f\x7f]", " ", (value or "")).strip()
    return value[:max_len]


def _int_arg(name: str, default: int, minimum: int, maximum: int) -> int:
    """Parse a bounded integer query parameter without ever raising a 500."""
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def _get_thread_loop() -> asyncio.AbstractEventLoop:
    """Return a reusable event loop for the current worker thread.

    ``asyncio.get_event_loop()`` raises in worker threads and the previous
    fallback created (and leaked) a brand-new loop on every request. Reusing a
    loop per thread keeps the shared httpx connection pool usable and avoids
    "Event loop is closed" errors under load.
    """
    loop = getattr(_thread_state, "loop", None)
    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        _thread_state.loop = loop
        _LOOPS.add(loop)
    return loop


def _run_coro_in_new_thread(coro, timeout: int):
    """Run a coroutine in a short-lived thread when this thread already has a
    running loop (e.g. an async view or a framework that manages its own)."""
    outcome: dict = {}

    def _runner():
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            outcome["value"] = loop.run_until_complete(
                asyncio.wait_for(coro, timeout=timeout)
            )
        except BaseException as exc:  # propagated to the calling thread
            outcome["error"] = exc
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            loop.close()

    thread = threading.Thread(target=_runner, name="lyrica-async", daemon=True)
    thread.start()
    thread.join(timeout + 5)
    if thread.is_alive():
        raise TimeoutError("Request timed out - operation took too long")
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("value")


def run_async(coro, timeout=30):
    """Run an async coroutine safely from a synchronous Flask view.

    Raises :class:`TimeoutError` (HTTP 504 at the route layer) rather than a
    generic exception, so clients receive the correct status code.
    """
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None

    if running is not None:
        return _run_coro_in_new_thread(coro, timeout)

    loop = _get_thread_loop()
    try:
        return loop.run_until_complete(asyncio.wait_for(coro, timeout=timeout))
    except (asyncio.TimeoutError, TimeoutError) as exc:
        logger.error("Async operation timed out after %ss", timeout)
        raise TimeoutError("Request timed out - operation took too long") from exc


def _serialize_json(obj) -> str:
    """Serialize with the app's orjson provider (fallback: stdlib json)."""
    try:
        return current_app.json.dumps(obj)
    except Exception:
        import json
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _cached_response(body: str, *, status: int = 200, cache_label: str = "HIT") -> Response:
    """Return a pre-serialized body with a strong ETag and 304 support."""
    etag = '"' + hashlib.sha256(body.encode("utf-8")).hexdigest()[:32] + '"'
    inm = request.headers.get("If-None-Match", "")
    candidates = {part.strip() for part in inm.split(",") if part.strip()}
    if "*" in candidates or etag in candidates:
        return Response(status=304, headers={"ETag": etag, "X-Cache": cache_label})
    response = Response(body, status=status, mimetype="application/json")
    response.headers["ETag"] = etag
    response.headers["X-Cache"] = cache_label
    return response


def _has_lyrics_content(result: dict | None) -> bool:
    if not isinstance(result, dict):
        return False
    data = result.get("data", result)
    if not isinstance(data, dict):
        return False
    if data.get("lyrics") or data.get("plain_lyrics") or data.get("lyrics_text"):
        return True
    return bool(data.get("timed_lyrics"))


def _get_raw_lyrics(
    artist: str,
    song: str,
    *,
    timestamps: bool,
    pass_param: bool,
    sequence,
    fast_mode: bool,
    fast_timeout: int,
    word_level: bool,
    syllabus: bool,
):
    """Resolve the richest-tier raw entry with negative caching + singleflight.

    Returns ``(result, tier, raw_key, meta)``. ``result`` is ``None`` when no
    provider had the song; ``meta["outcome"]`` distinguishes a clean absence
    from an error. Raises ``TimeoutError`` / ``Exception`` so the route can map
    them to 504/500 exactly as before.
    """
    raw_key = make_lyrics_cache_key(artist, song, sequence, pass_param)
    wanted = requested_tier(timestamps, word_level, syllabus)

    cached = load_raw(raw_key)
    if cached and tier_rank(cached[1]) >= tier_rank(wanted):
        return cached[0], cached[1], raw_key, {"outcome": "hit"}

    lower_tier_fallback = cached
    upgrade_marker = f"{raw_key}:tier:{wanted}"

    # A lower-tier entry already exists and an upgrade was attempted recently:
    # serve what we have instead of hammering providers on every request.
    if cached and negative_cache.get(upgrade_marker):
        return cached[0], cached[1], raw_key, {"outcome": "hit"}

    if negative_cache.get(raw_key):
        return None, None, raw_key, {"outcome": "not_found"}

    with singleflight.run(raw_key, timeout=70) as leader:
        if not leader:
            # The leader finished while we waited: re-check the shared cache
            # and the negative cache so duplicate requests get the same answer.
            cached = load_raw(raw_key)
            if cached:
                return cached[0], cached[1], raw_key, {"outcome": "hit"}
            if negative_cache.get(raw_key):
                return None, None, raw_key, {"outcome": "not_found"}
            return None, None, raw_key, {"outcome": "incomplete"}

        # Re-check inside the leader slot: another worker may have filled it
        # between the first lookup and acquiring the singleflight key.
        cached = load_raw(raw_key)
        if cached and tier_rank(cached[1]) >= tier_rank(wanted):
            return cached[0], cached[1], raw_key, {"outcome": "hit"}
        if not cached and negative_cache.get(raw_key):
            return None, None, raw_key, {"outcome": "not_found"}

        meta: dict = {}
        result = run_async(
            fetch_lyrics_controller(
                artist,
                song,
                timestamps=timestamps,
                pass_param=pass_param,
                sequence=sequence,
                fast_mode=fast_mode,
                fast_timeout=fast_timeout,
                word_level=word_level,
                syllabus=syllabus,
                meta=meta,
            ),
            timeout=60,
        )

        if result is not None and not isinstance(result, dict):
            meta["outcome"] = "invalid"
            return None, None, raw_key, meta

        if isinstance(result, dict) and result.get("status") == "success" and _has_lyrics_content(result):
            detected = detect_tier(result)
            # Never let a lower-tier upgrade attempt overwrite a richer entry.
            # This can happen when a word request falls back to a plain result
            # from a provider that is not the one that supplied the line entry.
            existing = load_raw(raw_key)
            if existing and tier_rank(existing[1]) >= tier_rank(detected):
                result, detected = existing[0], existing[1]
            else:
                try:
                    save_raw(raw_key, result, detected)
                except Exception as exc:
                    logger.warning("Raw cache save failed for %r - %r: %s", artist, song, exc)
            if tier_rank(detected) < tier_rank(wanted):
                negative_cache.set(upgrade_marker, "tier_unavailable")
            return result, detected, raw_key, meta

        if meta.get("outcome") == "not_found":
            negative_cache.set(raw_key, "not_found")
        elif meta.get("outcome") == "error":
            logger.warning(
                "All providers errored for %r - %r (attempts=%s, errors=%s)",
                artist,
                song,
                meta.get("attempts"),
                len(meta.get("errors", [])),
            )

        if lower_tier_fallback:
            # Remember that this tier could not be upgraded so the next request
            # for it serves the lower tier without another upstream call.
            negative_cache.set(upgrade_marker, "tier_unavailable")
            return lower_tier_fallback[0], lower_tier_fallback[1], raw_key, meta
        return None, None, raw_key, meta


def _run_ai_lines(data: dict, translate: bool, romanize: bool, language: str):
    """Run Groq on the lyric lines and return aligned (translated, romanized)."""
    timed = data.get("timed_lyrics") or []
    if timed:
        lines = [str(entry.get("text", "")) for entry in timed if isinstance(entry, dict)]
    else:
        raw = data.get("lyrics") or data.get("plain_lyrics") or ""
        lines = str(raw).split("\n") if raw else []
    if not lines:
        return None, None
    groq_result = run_async(
        process_lyrics(
            lyrics_lines=lines,
            target_language=language,
            translate=translate,
            romanize=romanize,
        ),
        timeout=120,
    )
    return groq_result.get("translated"), groq_result.get("romanized")


def register_routes(app):
    @app.route("/")
    def home():
        """Main API documentation endpoint"""
        return jsonify(
            {
                "api": "Lyrica",
                "version": app.config.get("VERSION", __version__),
                "status": "active",
                "description": "A comprehensive lyrics API with mood analysis, metadata extraction, and trending insights",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "endpoints": {
                    "lyrics": {
                        "url": "/lyrics/",
                        "method": "GET",
                        "description": "Fetch lyrics for a song",
                        "examples": [
                            "/lyrics/?artist=The Beatles&song=Imagine",
                            "/lyrics/?artist=The Beatles&song=Imagine&timestamps=true",
                            "/lyrics/?artist=The Beatles&song=Imagine&mood=true",
                            "/lyrics/?artist=The Beatles&song=Imagine&metadata=true",
                            "/lyrics/?artist=The Beatles&song=Imagine&translate=true&language=en",
                            "/lyrics/?artist=The Beatles&song=Imagine&romanize=true&language=hindi",
                            "/lyrics/?artist=The Beatles&song=Imagine&timestamps=true&translate=true&romanize=true&language=en",
                            "/lyrics/?artist=The Beatles&song=Imagine&fast=true&timestamps=true&mood=true&metadata=true"
                        ]
                    },
                    "metadata_only": {
                        "url": "/metadata/",
                        "method": "GET",
                        "description": "Get song metadata without lyrics",
                        "examples": [
                            "/metadata/?artist=The Beatles&song=Imagine"
                        ]
                    },
                    "trending": {
                        "url": "/trending/",
                        "method": "GET",
                        "description": "Get trending songs by country",
                        "examples": [
                            "/trending/?country=US&limit=20",
                            "/trending/?country=IN",
                            "/trending/?countries=US,GB,IN&limit=10"
                        ]
                    },
                    "top_queries": {
                        "url": "/analytics/top-queries/",
                        "method": "GET",
                        "description": "Get top user queries globally or by country",
                        "examples": [
                            "/analytics/top-queries/?limit=20",
                            "/analytics/top-queries/?country=US&limit=10",
                            "/analytics/top-queries/?country=US&days=7&limit=15"
                        ]
                    },
                    "trending_by_country": {
                        "url": "/analytics/trending-by-country/",
                        "method": "GET",
                        "description": "Get top queries for each country",
                        "examples": [
                            "/analytics/trending-by-country/?limit=10"
                        ]
                    },
                    "trending_vs_queries": {
                        "url": "/analytics/trending-vs-queries/",
                        "method": "GET",
                        "description": "Compare trending songs with top user queries",
                        "examples": [
                            "/analytics/trending-vs-queries/?country=US&limit=10"
                        ]
                    },
                    "trending_intersection": {
                        "url": "/analytics/trending-intersection/",
                        "method": "GET",
                        "description": "Find queries that match trending songs",
                        "examples": [
                            "/analytics/trending-intersection/?country=US&limit=10"
                        ]
                    },
                    "jiosaavn_search": {
                        "url": "/api/jiosaavn/search",
                        "method": "GET",
                        "description": "Search for songs on JioSaavn",
                        "examples": [
                            "/api/jiosaavn/search?q=Imagine"
                        ]
                    },
                    "jiosaavn_play": {
                        "url": "/api/jiosaavn/play",
                        "method": "GET",
                        "description": "Get playable stream URL from JioSaavn",
                        "examples": [
                            "/api/jiosaavn/play?songLink=<song_link>"
                        ]
                    },
                    "cache_stats": {
                        "url": "/cache/stats",
                        "method": "GET",
                        "description": "Get cache statistics"
                    },
                    "suggestion": {
                        "url": "/suggestion",
                        "method": "GET",
                        "description": "Search for songs by name and return matching titles with their artist",
                        "examples": [
                            "/suggestion?q=Imagine",
                            "/suggestion?q=Imagine&limit=5"
                        ]
                    },
                    "music_app": {
                        "url": "/app",
                        "method": "GET",
                        "description": "Access the web-based music application"
                    }
                },
                "parameters": {
                    "artist": {
                        "type": "string",
                        "required": True,
                        "description": "Artist name"
                    },
                    "song": {
                        "type": "string",
                        "required": True,
                        "description": "Song title"
                    },
                    "country": {
                        "type": "string",
                        "required": False,
                        "description": "Country code (US, GB, IN, BR, JP, DE, FR, CA, AU, MX)"
                    },
                    "countries": {
                        "type": "string",
                        "required": False,
                        "description": "Comma-separated country codes"
                    },
                    "limit": {
                        "type": "integer",
                        "required": False,
                        "default": 20,
                        "description": "Number of results to return"
                    },
                    "days": {
                        "type": "integer",
                        "required": False,
                        "description": "Time window in days for query analytics"
                    },
                    "timestamps": {
                        "type": "boolean",
                        "required": False,
                        "default": False,
                        "description": "Include synchronized timestamps with lyrics"
                    },
                    "mood": {
                        "type": "boolean",
                        "required": False,
                        "default": False,
                        "description": "Analyze song mood/sentiment and top words"
                    },
                    "metadata": {
                        "type": "boolean",
                        "required": False,
                        "default": False,
                        "description": "Include song metadata (cover art, duration, genre, etc.)"
                    },
                    "fast": {
                        "type": "boolean",
                        "required": False,
                        "default": False,
                        "description": "Use parallel fetching for faster results"
                    },
                    "translate": {
                        "type": "boolean",
                        "required": False,
                        "default": False,
                        "description": "Translate lyrics to target language (requires GROQ_API_KEY)"
                    },
                    "romanize": {
                        "type": "boolean",
                        "required": False,
                        "default": False,
                        "description": "Romanize/transliterate lyrics to target language script (requires GROQ_API_KEY)"
                    },
                    "language": {
                        "type": "string",
                        "required": False,
                        "default": "en",
                        "description": "Target language for translate/romanize (e.g., en, hindi, spanish, japanese)"
                    },
                    "word": {
                        "type": "boolean",
                        "required": False,
                        "default": False,
                        "description": "Request word-level synced lyrics (e.g., from Lrcmux or Apple Music)"
                    },
                    "syllabus": {
                        "type": "boolean",
                        "required": False,
                        "default": False,
                        "description": "Request syllable-level synced lyrics (Apple Music only)"
                    }
                },
                "fetchers": {
                    "1": "Genius (requires GENIUS_TOKEN)",
                    "2": "LRCLIB",
                    "3": "YouTube Music (3-layer: ytmusicapi [authenticated] / transcript-api / yt-dlp)",
                    "4": "NetEase (via syncedlyrics, synced LRC)",
                    "5": "Megallobiz (via syncedlyrics, synced LRC)",
                    "6": "Musixmatch (via syncedlyrics, optional MUSIXMATCH_TOKEN)",
                    "7": "Lrcmux (via api.lrcmux.dev, Musixmatch lyrics; supports word-level sync with &word=true)",
                    "8": "Apple Music (requires APPLE_MUSIC_DEVELOPER_TOKEN; syllable-level with &syllabus=true, word-level with &word=true)",
                }
            }
        )

    @app.route("/lyrics/", methods=["GET"])
    def lyrics():
        """Fetch lyrics with optional mood analysis and metadata"""
        # ── Load config defaults (query params always win) ────────────────
        try:
            cfg = get_user_config()
        except Exception:
            cfg = None

        raw_artist = request.args.get("artist", "")
        raw_song = request.args.get("song", "")
        artist = _sanitize_text(raw_artist)
        song = _sanitize_text(raw_song)
        country = _sanitize_text(request.args.get("country", "US"), 8).upper() or "US"

        if len(raw_artist.strip()) > _MAX_TEXT_LEN or len(raw_song.strip()) > _MAX_TEXT_LEN:
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": f"artist and song must each be at most {_MAX_TEXT_LEN} characters",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                400,
            )

        # Apply config defaults when query param not explicitly supplied
        _ts_default = (cfg.default_timestamps if cfg else False)
        timestamps = (
            request.args.get("timestamps", str(_ts_default)).lower() == "true"
            or request.args.get("timestamp",  str(_ts_default)).lower() == "true"
        )
        pass_param = request.args.get("pass", "false").lower() == "true"
        sequence   = request.args.get("sequence", cfg.default_sequence if cfg else None)
        if isinstance(sequence, str) and len(sequence) > 500:
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "sequence parameter is too long",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                400,
            )
        fast_mode  = request.args.get("fast",  str(cfg.default_fast     if cfg else False)).lower() == "true"
        analyze_mood      = request.args.get("mood",     str(cfg.default_mood     if cfg else False)).lower() == "true"
        include_metadata  = request.args.get("metadata", str(cfg.default_metadata if cfg else False)).lower() == "true"
        do_translate = request.args.get("translate", str(cfg.default_translate if cfg else False)).lower() == "true"
        do_romanize  = request.args.get("romanize",  str(cfg.default_romanize  if cfg else False)).lower() == "true"
        word_level   = request.args.get("word",      str(cfg.default_word      if cfg else False)).lower() == "true"
        syllabus     = request.args.get("syllabus",  "false").lower() == "true"
        target_language = _sanitize_text(
            request.args.get("language", cfg.default_language if cfg else "en"), 40
        ).lower() or "en"
        _fast_timeout = cfg.fast_timeout if cfg else 20

        if not artist or not song:
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Artist and song name are required",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                400,
            )

        if pass_param and not sequence:
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Sequence parameter is required when pass=true",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                400,
            )

        logger.info(
            f"Lyrics request: {artist} - {song} (fast={fast_mode}, mood={analyze_mood}, "
            f"metadata={include_metadata}, translate={do_translate}, romanize={do_romanize}, "
            f"word={word_level}, syllabus={syllabus}, lang={target_language})"
        )

        # Record user query for analytics
        try:
            trending_engine.record_user_query(
                user_id=request.remote_addr,
                query=f"{artist} - {song}",
                country=country
            )
        except Exception as e:
            logger.warning(f"Failed to record user query: {str(e)}")

        # 1. Rendered-view cache. The body is stored pre-serialized so a hit
        #    skips tier derivation and JSON encoding entirely.
        view_key = make_view_cache_key(
            artist,
            song,
            timestamps=timestamps,
            sequence=sequence,
            mood=analyze_mood,
            metadata=include_metadata,
            translate=do_translate,
            romanize=do_romanize,
            language=target_language,
            word_level=word_level,
            syllabus=syllabus,
            pass_param=pass_param,
        )
        cached_view = load_view(view_key)
        if cached_view:
            _, cached_body = cached_view
            logger.info("View cache hit for %s - %s", artist, song)
            return _cached_response(cached_body)

        # 2. Raw lyrics entry, shared by every flag combination, with
        #    singleflight coalescing and a short negative cache.
        try:
            raw_result, _raw_tier, _raw_key, _raw_meta = _get_raw_lyrics(
                artist,
                song,
                timestamps=timestamps,
                pass_param=pass_param,
                sequence=sequence,
                fast_mode=fast_mode,
                fast_timeout=_fast_timeout,
                word_level=word_level,
                syllabus=syllabus,
            )
        except TimeoutError:
            logger.error(f"Timeout fetching lyrics for {artist} - {song}")
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Request timed out",
                        "details": "Lyrics fetch took too long",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                504,
            )
        except Exception as e:
            logger.error(f"Error fetching lyrics: {str(e)}")
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Failed to fetch lyrics",
                        **_error_details(e),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                500,
            )

        if raw_result is None:
            if _raw_meta.get("outcome") == "invalid":
                return (
                    jsonify({
                        "status": "error",
                        "error": {
                            "message": "Invalid response from lyrics fetcher",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    }),
                    500,
                )
            logger.info("No lyrics found for %s - %s", artist, song)
            return jsonify({
                "status": "error",
                "error": {
                    "message": "No lyrics found",
                    "details": "All enabled fetchers returned no result",
                },
            })

        result = derive_view(
            raw_result,
            requested_tier(timestamps, word_level, syllabus),
        )

        # 3. Analyze mood if requested
        if analyze_mood and result.get("status") == "success":
            data = result.get("data", {})
            lyrics_text = extract_lyrics_text(data)

            if lyrics_text:
                try:
                    sentiment = analyze_sentiment(lyrics_text)
                    word_freq = analyze_word_frequency(lyrics_text, top_n=5)

                    result["mood_analysis"] = {
                        "sentiment": sentiment,
                        "top_words": word_freq,
                    }
                    logger.info(f"Mood analysis completed for {artist} - {song}")
                except Exception as e:
                    logger.warning(f"Mood analysis failed: {str(e)}")
                    result["mood_analysis"] = {
                        "error": "Unable to perform mood analysis",
                        **_error_details(e),
                    }
            else:
                logger.warning("Could not extract lyrics for mood analysis")
                result["mood_analysis"] = {"error": "Unable to extract lyrics for analysis"}

        # 4. Include metadata if requested
        if include_metadata and result.get("status") == "success":
            try:
                metadata_result = enhance_lyrics_with_metadata(result, artist, song)
                if asyncio.iscoroutine(metadata_result):
                    metadata_result = run_async(metadata_result, timeout=30)
                result = metadata_result
                logger.info(f"Metadata enhanced for {artist} - {song}")
            except Exception as e:
                logger.warning(f"Metadata enhancement failed: {str(e)}")
                result["metadata_error"] = "Could not retrieve metadata"
                if not _IS_PRODUCTION:
                    result["metadata_error"] += f": {e}"

        # 5. Translate / Romanize if requested
        if (do_translate or do_romanize) and result.get("status") == "success":
            data = result.get("data", {})

            # Check if Groq keys are configured
            if not get_key_manager().has_keys:
                return (
                    jsonify({
                        "status": "error",
                        "error": {
                            "message": "Translation/romanization requires a Groq API key. "
                                       "Set GROQ_API_KEY in your .env file.",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    }),
                    503,
                )

            # Check translation cache first
            trans_cache_key = make_translation_cache_key(
                artist, song,
                data.get("source", "unknown"),
                target_language,
                do_translate, do_romanize,
                data.get("hasTimestamps", False),
            )
            cached_translation = load_translation_cache(trans_cache_key)

            if cached_translation:
                # Merge cached translation into result
                result = cached_translation
                logger.info(f"Translation cache hit for {artist} - {song}")
            else:
                # Extract lyric lines for LLM processing
                has_timed = data.get("hasTimestamps", False) and data.get("timed_lyrics")

                if has_timed:
                    lyrics_lines = [entry.get("text", "") for entry in data["timed_lyrics"]]
                else:
                    raw_lyrics = data.get("lyrics", "")
                    lyrics_lines = raw_lyrics.split("\n") if raw_lyrics else []

                if lyrics_lines:
                    try:
                        groq_result = run_async(
                            process_lyrics(
                                lyrics_lines=lyrics_lines,
                                target_language=target_language,
                                translate=do_translate,
                                romanize=do_romanize,
                            ),
                            timeout=120,
                        )

                        translated_lines = groq_result.get("translated")
                        romanized_lines = groq_result.get("romanized")
                        metadata = groq_result.get("metadata", {})

                        # Add translation_metadata to data
                        data["translation_metadata"] = {
                            "target_language": metadata.get("target_language", target_language),
                            "processed_by": metadata.get("processed_by", f"groq/{GROQ_MODEL}"),
                            "cached_from": "fresh",
                        }


                        if has_timed:
                            # Synced lyrics: add romanized/translated to each timed_lyrics entry
                            for i, entry in enumerate(data["timed_lyrics"]):
                                if do_translate and translated_lines and i < len(translated_lines):
                                    entry["translated"] = translated_lines[i]
                                if do_romanize and romanized_lines and i < len(romanized_lines):
                                    entry["romanized"] = romanized_lines[i]
                        else:
                            # Unsynced lyrics: add as top-level strings
                            if do_translate and translated_lines:
                                data["translated_lyrics"] = "\n".join(translated_lines)
                            if do_romanize and romanized_lines:
                                data["romanized_lyrics"] = "\n".join(romanized_lines)

                        result["data"] = data

                        # Save to translation cache
                        try:
                            save_translation_cache(trans_cache_key, result)
                            logger.info(f"Translation cached for {artist} - {song}")
                        except Exception as e:
                            logger.warning(f"Translation cache save failed: {str(e)}")

                        logger.info(f"Translation/romanization completed for {artist} - {song}")

                    except Exception as e:
                        logger.error(f"Translation/romanization failed: {str(e)}")
                        result["translation_error"] = "Translation processing failed"
                        if not _IS_PRODUCTION:
                            result["translation_error"] += f": {e}"

        # 6. Cache the rendered view (including mood/metadata/translation).
        if result.get("status") == "success":
            try:
                body = _serialize_json(result)
                save_view(view_key, result, body)
                logger.info(f"Result cached for {artist} - {song}")
                return _cached_response(body, cache_label="MISS")
            except Exception as e:
                logger.warning(f"Cache save failed: {str(e)}")

        return jsonify(result)

    @app.route("/v2/lyrics", methods=["GET"])
    def v2_lyrics():
        """Lean v2 lyrics endpoint with ETag/304 and tier derivation."""
        raw_artist = request.args.get("artist", "")
        raw_song = request.args.get("song", "")
        artist = _sanitize_text(raw_artist)
        song = _sanitize_text(raw_song)
        if not artist or not song:
            return jsonify({"err": "missing_artist_or_song"}), 400

        tier = normalize_tier(request.args.get("tier", "line"))
        if tier is None:
            return jsonify({"err": "bad_tier", "allowed": list(TIERS)}), 400

        allow_lower = request.args.get("allow_lower", "true").lower() != "false"
        lite = request.args.get("lite", "false").lower() == "true"
        fields_raw = request.args.get("fields", "")
        fields = {part.strip() for part in fields_raw.split(",") if part.strip()} or None
        do_translate = request.args.get("translate", "false").lower() == "true"
        do_romanize = request.args.get("romanize", "false").lower() == "true"
        target_language = _sanitize_text(request.args.get("lang", "en"), 40).lower() or "en"
        fast_mode = request.args.get("fast", "false").lower() == "true"

        timestamps = tier != "plain"
        word_level = tier in ("word", "syllable")
        syllabus = tier == "syllable"

        view_key = make_view_cache_key(
            artist,
            song,
            timestamps=timestamps,
            mood=False,
            metadata=False,
            translate=do_translate,
            romanize=do_romanize,
            language=target_language,
            word_level=word_level,
            syllabus=syllabus,
            extra={
                "v2": 1,
                "tier": tier,
                "lite": lite,
                "fields": sorted(fields) if fields else [],
            },
        )
        cached_view = load_view(view_key)
        if cached_view:
            return _cached_response(cached_view[1])

        try:
            raw_result, _raw_tier, _raw_key, raw_meta = _get_raw_lyrics(
                artist,
                song,
                timestamps=timestamps,
                pass_param=False,
                sequence=None,
                fast_mode=fast_mode,
                fast_timeout=20,
                word_level=word_level,
                syllabus=syllabus,
            )
        except TimeoutError:
            return jsonify({"err": "timeout"}), 504
        except Exception as exc:
            logger.error("v2 fetch failed for %r - %r: %s", artist, song, exc)
            return jsonify({"err": "internal"}), 500

        if raw_result is None:
            if raw_meta.get("outcome") == "not_found":
                return jsonify({"err": "not_found"}), 404
            return jsonify({"err": "upstream_unavailable"}), 503

        actual = detect_tier(raw_result)
        if tier_rank(actual) < tier_rank(tier) and not allow_lower:
            return jsonify({"err": "tier_unavailable", "tier": actual}), 404

        derived = derive_view(raw_result, tier)
        effective_tier = tier if tier_rank(tier) <= tier_rank(actual) else actual

        translated = romanized = None
        if do_translate or do_romanize:
            if not get_key_manager().has_keys:
                return jsonify({"err": "ai_unavailable"}), 503
            try:
                translated, romanized = _run_ai_lines(
                    derived.get("data", derived),
                    do_translate,
                    do_romanize,
                    target_language,
                )
            except Exception as exc:
                logger.error("v2 AI processing failed for %r - %r: %s", artist, song, exc)
                return jsonify({"err": "ai_failed"}), 502

        payload = to_lean(derived, effective_tier, lite=lite, fields=fields)
        if translated:
            payload["tr"] = translated
        if romanized:
            payload["rom"] = romanized

        body = _serialize_json(payload)
        try:
            save_view(view_key, payload, body)
        except Exception as exc:
            logger.warning("v2 view cache save failed: %s", exc)
        return _cached_response(body, cache_label="MISS")

    @app.route("/v2/capabilities", methods=["GET"])
    def v2_capabilities():
        """Describe what this instance supports."""
        try:
            ai_available = get_key_manager().has_keys
        except Exception:
            ai_available = False
        return jsonify({
            "v": 2,
            "tiers": list(TIERS),
            "providers": sorted(ALL_FETCHERS.keys()),
            "ai": ai_available,
            "byok": False,
            "compression": os.getenv("LYRICA_COMPRESS", "false").lower() in ("1", "true", "yes"),
        })

    @app.route("/v2/health", methods=["GET"])
    def v2_health():
        """Provider breaker/quota state, queue stats, and cache stats."""
        stats = cache_stats()
        stats.pop("cache_dir", None)
        return jsonify({
            "v": 2,
            "status": "ok",
            "providers": providers.snapshot(),
            "singleflight": singleflight.stats(),
            "negative_cache": negative_cache.stats(),
            "cache": stats,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    @app.route("/metadata/", methods=["GET"])
    def metadata():
        """Get song metadata only (without lyrics)"""
        raw_artist = request.args.get("artist", "")
        raw_song = request.args.get("song", "")
        artist = _sanitize_text(raw_artist)
        song = _sanitize_text(raw_song)

        if len(raw_artist.strip()) > _MAX_TEXT_LEN or len(raw_song.strip()) > _MAX_TEXT_LEN:
            return jsonify({
                "status": "error",
                "error": {
                    "message": f"artist and song must each be at most {_MAX_TEXT_LEN} characters",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            }), 400

        if not artist or not song:
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Artist and song name are required",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                400,
            )

        logger.info(f"Metadata request for {artist} - {song}")
        
        try:
            result = get_metadata_only(artist, song)
            if asyncio.iscoroutine(result):
                result = run_async(result, timeout=30)
        except TimeoutError:
            logger.error(f"Timeout fetching metadata for {artist} - {song}")
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Request timed out",
                        "details": "Metadata fetch took too long",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                504,
            )
        except Exception as e:
            logger.error(f"Metadata fetch error: {str(e)}")
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Failed to fetch metadata",
                        **_error_details(e),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                500,
            )

        return jsonify(result)

    @app.route("/trending/", methods=["GET"])
    def trending():
        """Get trending songs by country"""
        country = _sanitize_text(request.args.get("country", "US"), 8).upper() or "US"
        countries_param = _sanitize_text(request.args.get("countries", ""), 64)
        limit = _int_arg("limit", 20, 1, 100)

        logger.info(f"Trending request: country={country}, limit={limit}")

        try:
            # Handle single country
            if country and not countries_param:
                try:
                    country_enum = Country[country]
                    trending_songs = trending_engine.fetch_trending_songs(country_enum, limit)
                    
                    return jsonify({
                        "status": "success",
                        "data": {
                            "country": country,
                            "trending": [song.to_dict() for song in trending_songs],
                            "total": len(trending_songs),
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                    })
                except KeyError:
                    return jsonify({
                        "status": "error",
                        "error": {
                            "message": f"Invalid country code: {country}",
                            "valid_countries": [c.value for c in Country],
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                    }), 400

            # Handle multiple countries
            elif countries_param:
                country_list = [c.strip().upper() for c in countries_param.split(",")]
                trending_data = {}
                
                for c in country_list:
                    try:
                        country_enum = Country[c]
                        trending_songs = trending_engine.fetch_trending_songs(country_enum, limit)
                        trending_data[c] = [song.to_dict() for song in trending_songs]
                    except KeyError:
                        logger.warning(f"Invalid country code: {c}")
                        continue

                return jsonify({
                    "status": "success",
                    "data": {
                        "countries": trending_data,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                })

        except Exception as e:
            logger.error(f"Trending fetch error: {str(e)}")
            return jsonify({
                "status": "error",
                "error": {
                    "message": "Failed to fetch trending data",
                    **_error_details(e),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            }), 500

    @app.route("/analytics/top-queries/", methods=["GET"])
    def top_queries():
        """Get top user queries globally or by country"""
        limit = _int_arg("limit", 20, 1, 100)
        country = _sanitize_text(request.args.get("country", ""), 8).upper()
        days_raw = request.args.get("days")
        days = _int_arg("days", 0, 0, 3650) if days_raw else None

        if days is not None and days <= 0:
            days = None

        logger.info(f"Top queries request: limit={limit}, country={country}, days={days}")

        try:
            top_q = trending_engine.get_top_queries(
                limit=limit,
                country=country if country else None,
                days=days
            )

            return jsonify({
                "status": "success",
                "data": {
                    "scope": "global" if not country else f"country_{country}",
                    "time_window": f"{days} days" if days else "all_time",
                    "top_queries": [{"query": q, "count": c} for q, c in top_q],
                    "total_unique": len(top_q),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            })

        except Exception as e:
            logger.error(f"Top queries fetch error: {str(e)}")
            return jsonify({
                "status": "error",
                "error": {
                    "message": "Failed to fetch top queries",
                    **_error_details(e),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            }), 500

    @app.route("/analytics/trending-by-country/", methods=["GET"])
    def trending_by_country():
        """Get top queries for each country"""
        limit = _int_arg("limit", 10, 1, 100)

        logger.info(f"Trending by country request: limit={limit}")

        try:
            top_by_country = trending_engine.get_top_queries_by_country(limit=limit)

            return jsonify({
                "status": "success",
                "data": {
                    "countries": {
                        country: [{"query": q, "count": c} for q, c in queries]
                        for country, queries in top_by_country.items()
                    },
                    "total_countries": len(top_by_country),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            })

        except Exception as e:
            logger.error(f"Trending by country error: {str(e)}")
            return jsonify({
                "status": "error",
                "error": {
                    "message": "Failed to fetch trending by country",
                    **_error_details(e),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            }), 500

    @app.route("/analytics/trending-vs-queries/", methods=["GET"])
    def trending_vs_queries():
        """Compare trending songs with top user queries"""
        country = _sanitize_text(request.args.get("country", "US"), 8).upper() or "US"
        limit = _int_arg("limit", 10, 1, 100)

        logger.info(f"Trending vs queries request: country={country}, limit={limit}")

        try:
            country_enum = Country[country]
            comparison = trending_engine.get_trending_vs_user_queries(country_enum, limit)

            return jsonify({
                "status": "success",
                "data": comparison
            })

        except KeyError:
            return jsonify({
                "status": "error",
                "error": {
                    "message": f"Invalid country code: {country}",
                    "valid_countries": [c.value for c in Country],
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            }), 400
        except Exception as e:
            logger.error(f"Trending vs queries error: {str(e)}")
            return jsonify({
                "status": "error",
                "error": {
                    "message": "Failed to fetch trending vs queries",
                    **_error_details(e),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            }), 500

    @app.route("/analytics/trending-intersection/", methods=["GET"])
    def trending_intersection():
        """Find queries that match trending songs"""
        country = _sanitize_text(request.args.get("country", "US"), 8).upper() or "US"
        limit = _int_arg("limit", 10, 1, 100)

        logger.info(f"Trending intersection request: country={country}, limit={limit}")

        try:
            country_enum = Country[country]
            matches = trending_engine.get_trending_intersection(country_enum, limit)

            return jsonify({
                "status": "success",
                "data": {
                    "country": country,
                    "matches": matches,
                    "total_matches": len(matches),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            })

        except KeyError:
            return jsonify({
                "status": "error",
                "error": {
                    "message": f"Invalid country code: {country}",
                    "valid_countries": [c.value for c in Country],
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            }), 400
        except Exception as e:
            logger.error(f"Trending intersection error: {str(e)}")
            return jsonify({
                "status": "error",
                "error": {
                    "message": "Failed to fetch trending intersection",
                    **_error_details(e),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            }), 500

    @app.route("/api/jiosaavn/search", methods=["GET"])
    def jiosaavn_search():
        """Search for songs on JioSaavn"""
        query = _sanitize_text(request.args.get("q", ""))
        
        if not query:
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Query parameter 'q' is required",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                400,
            )

        logger.info(f"JioSaavn search query: {query}")
        
        try:
            results = search_jiosaavn(query)
            if asyncio.iscoroutine(results):
                results = run_async(results, timeout=30)
            return jsonify({"status": "success", "results": results})
        except asyncio.TimeoutError:
            logger.error(f"Timeout searching JioSaavn for: {query}")
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Request timed out",
                        "details": "JioSaavn search took too long",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                504,
            )
        except Exception as e:
            logger.error(f"JioSaavn search error: {str(e)}")
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Failed to search JioSaavn",
                        **_error_details(e),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                500,
            )

    @app.route("/api/jiosaavn/play", methods=["GET"])
    def jiosaavn_play():
        """Get playable stream URL from JioSaavn"""
        song_link = _sanitize_text(request.args.get("songLink", ""), 2048)
        
        if not song_link:
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "songLink parameter is required",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                400,
            )

        logger.info(f"JioSaavn play request for: {song_link}")
        
        try:
            data = get_jiosaavn_stream(song_link)
            if asyncio.iscoroutine(data):
                data = run_async(data, timeout=30)
            
            if not data or not isinstance(data, dict):
                return (
                    jsonify({
                        "status": "error",
                        "error": {
                            "message": "Invalid response from JioSaavn",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    }),
                    500,
                )

            if not data.get("stream_url"):
                return (
                    jsonify({
                        "status": "error",
                        "error": {
                            "message": "Unable to fetch stream URL",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    }),
                    500,
                )

            return jsonify({"status": "success", "data": data})
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching stream for: {song_link}")
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Request timed out",
                        "details": "Stream fetch took too long",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                504,
            )
        except Exception as e:
            logger.error(f"JioSaavn play error: {str(e)}")
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Failed to fetch stream",
                        **_error_details(e),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                500,
            )

    @app.route("/suggestion", methods=["GET"])
    def suggestion():
        """Search MusicBrainz for songs matching a query and return title + artist"""
        query = _sanitize_text(request.args.get("q", ""))
        limit = _int_arg("limit", 10, 1, 100)

        if not query:
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Query parameter 'q' is required",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                400,
            )

        logger.info(f"Suggestion request: q={query}, limit={limit}")

        try:
            resp = _SUGGESTION_CLIENT.get(
                "https://musicbrainz.org/ws/2/recording/",
                params={"query": query, "fmt": "json", "limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()
        except _httpx.TimeoutException:
            logger.error(f"Timeout querying MusicBrainz for: {query}")
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Request timed out while contacting MusicBrainz",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                504,
            )
        except Exception as e:
            logger.error(f"MusicBrainz suggestion error: {str(e)}")
            # The client request was valid; the upstream service failed. A 5xx
            # here is expected and must not look like an unhandled application
            # crash (500), so surface it as 502 Bad Gateway.
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Suggestion service is temporarily unavailable",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                502,
            )

        recordings = data.get("recordings", [])
        results = []
        for rec in recordings:
            title = rec.get("title", "")
            artist_credits = rec.get("artist-credit", [])
            artist_parts = []
            for credit in artist_credits:
                if isinstance(credit, dict) and "artist" in credit:
                    artist_parts.append(credit["artist"].get("name", ""))
                    artist_parts.append(credit.get("joinphrase", ""))
                elif isinstance(credit, str):
                    artist_parts.append(credit)
            artist = "".join(artist_parts).strip() or "Unknown Artist"
            results.append({"title": title, "artist": artist})

        return jsonify({
            "status": "success",
            "query": query,
            "limit": limit,
            "total": len(results),
            "results": results,
        })

    @app.route("/app", methods=["GET"])
    def app_page():
        """Serve the web-based music application"""
        try:
            return render_template("index.html")
        except Exception as e:
            logger.error(f"Failed to render app page: {str(e)}")
            return jsonify({
                "status": "error",
                "error": {
                    "message": "Failed to load application",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            }), 500

    @app.route("/cache/stats", methods=["GET"])
    def route_cache_stats():
        """Get cache statistics and information"""
        try:
            stats = cache_stats()
            # Public endpoint: do not disclose host filesystem paths.
            stats.pop("cache_dir", None)
            return jsonify({"status": "success", **stats})
        except Exception as e:
            logger.error(f"Cache stats error: {str(e)}")
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Failed to retrieve cache stats",
                        **_error_details(e),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                500,
            )

    @app.route("/cache/clear", methods=["POST"])
    def route_clear_cache():
        """Clear all cached data (Admin only)"""
        # Require admin key via header (preferred) or query param (legacy)
        key = request.headers.get("X-ADMIN-KEY") or request.args.get("key")
        if not _admin_key_ok(key):
            return (
                jsonify({"status": "error", "error": {"message": "Unauthorized"}}),
                403,
            )
        try:
            res = clear_cache()
            logger.info("Cache cleared")
            return jsonify({"status": "success", "details": res})
        except Exception as e:
            logger.error(f"Cache clear error: {str(e)}")
            return (
                jsonify({
                    "status": "error",
                    "error": {
                        "message": "Failed to clear cache",
                        **_error_details(e),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }),
                500,
            )

    @app.route("/favicon.ico", methods=["GET"])
    def favicon():
        """Favicon endpoint"""
        return "", 204

    # ─────────────────────────────────────────────────────────────────────────
    # Proxy management endpoints (admin-key protected)
    # ─────────────────────────────────────────────────────────────────────────

    def _admin_check():
        """Return (True, None) if admin key is valid, else (False, response)."""
        key = request.headers.get("X-ADMIN-KEY") or request.args.get("key")
        if not _admin_key_ok(key):
            return False, (jsonify({"status": "error", "error": {"message": "Unauthorized — admin key required"}}), 403)
        return True, None

    @app.route("/v2/proxy/set", methods=["POST"])
    def proxy_set():
        """Add a proxy to the pool (admin-key protected)"""
        ok, err = _admin_check()
        if not ok:
            return err

        body = request.get_json(silent=True) or {}
        proxy_url = _sanitize_text(body.get("proxy") or request.args.get("proxy", ""), 2048)

        if not proxy_url:
            return jsonify({"status": "error", "error": {"message": "`proxy` field is required"}}), 400

        added = get_proxy_manager().add(proxy_url)
        return jsonify({
            "status":  "success" if added else "skipped",
            "message": "Proxy added" if added else "Proxy already in pool or invalid",
            "pool_size": get_proxy_manager().size(),
        })

    @app.route("/v2/proxy/remove", methods=["DELETE", "POST"])
    def proxy_remove():
        """Remove a proxy from the pool by URL (admin-key protected)"""
        ok, err = _admin_check()
        if not ok:
            return err

        body = request.get_json(silent=True) or {}
        proxy_url = _sanitize_text(body.get("proxy") or request.args.get("proxy", ""), 2048)

        if not proxy_url:
            return jsonify({"status": "error", "error": {"message": "`proxy` field is required"}}), 400

        removed = get_proxy_manager().remove(proxy_url)
        return jsonify({
            "status":  "success" if removed else "not_found",
            "message": "Proxy removed" if removed else "Proxy not found in pool",
            "pool_size": get_proxy_manager().size(),
        })

    @app.route("/v2/proxy/list", methods=["GET"])
    def proxy_list():
        """List all proxies with masked credentials (admin-key protected)"""
        ok, err = _admin_check()
        if not ok:
            return err

        return jsonify({
            "status":  "success",
            "pool_size": get_proxy_manager().size(),
            "proxies": get_proxy_manager().list_masked(),
        })

    @app.route("/v2/proxy/clear", methods=["POST"])
    def proxy_clear():
        """Remove all proxies from the pool (admin-key protected)"""
        ok, err = _admin_check()
        if not ok:
            return err

        count = get_proxy_manager().clear()
        return jsonify({
            "status":  "success",
            "message": f"{count} proxies removed",
            "pool_size": 0,
        })

    # ─────────────────────────────────────────────────────────────────────────
    # NEW: Config management endpoints
    # ─────────────────────────────────────────────────────────────────────────

    @app.route("/config/status", methods=["GET"])
    def config_status():
        """Show currently loaded config file and effective settings"""
        try:
            cfg = get_user_config()
            return jsonify({
                "status": "success",
                "config": cfg.to_dict(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:
            logger.error(f"Config status error: {e}")
            return jsonify({"status": "error", "error": {"message": str(e)}}), 500

    @app.route("/config/reload", methods=["POST"])
    def config_reload():
        """Force config file reload without restarting the server (admin-key protected)"""
        ok, err = _admin_check()
        if not ok:
            return err

        try:
            cfg = reload_user_config()
            return jsonify({
                "status":  "success",
                "message": "Config reloaded",
                "config":  cfg.to_dict(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:
            logger.error(f"Config reload error: {e}")
            return jsonify({"status": "error", "error": {"message": str(e)}}), 500

'''
 @app.route("/debug/trending-raw", methods=["GET"])
def debug_trending_raw():
    """Debug endpoint to see raw trending data"""
    from src.trending_analytics import trending_engine, Country
    raw = trending_engine.ytmusic.get_trending(region="US")
    return jsonify({
        "type": str(type(raw)),
        "keys": list(raw.keys()) if isinstance(raw, dict) else "is_list",
        "first_item": raw[0] if isinstance(raw, list) and raw else (list(raw.items())[0] if isinstance(raw, dict) else None)
    })
'''