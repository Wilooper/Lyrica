# Lyrica — Agent Rules & Project Conventions

## Project Overview

Lyrica is a **Python/Flask REST API** (v1.4.0) that aggregates song lyrics from multiple sources (Genius, LRCLIB, YouTube Music, NetEase, Megalobiz, Musixmatch, Lrcmux) with optional mood analysis, metadata enrichment, trending analytics, word-level sync, and lyrics translation/romanization via Groq LLM.

## Tech Stack

- **Framework**: Flask 3.0 (with async view support)
- **HTTP Client**: `httpx` (async) — used by all fetchers, never `requests` for new code
- **Server**: Gunicorn (production), Flask dev server (local)
- **Python**: 3.11+
- **Config**: `.env` for secrets, `.lyrica.config` (INI format) for user preferences
- **Cache**: File-based JSON cache in `cache_data/` directory

## Architecture

```
lyrica/
├── run.py                  # Entry point
├── src/
│   ├── __init__.py         # Package version (currently 1.4.0)
│   ├── app.py              # Flask app factory (create_app); seeds proxy pool from PROXY_URL env
│   ├── router.py           # All route handlers
│   ├── config.py           # Environment variable loading
│   ├── user_config.py      # .lyrica.config INI file parser
│   ├── cache.py            # File-based caching system
│   ├── fetch_controller.py # Orchestrates fetcher sequence; passes word_level to lrcmux
│   ├── logger.py           # Centralized logging
│   ├── proxy_manager.py    # Thread-safe round-robin proxy pool singleton
│   ├── groq_key_manager.py # Groq API multi-key round-robin & cooldowns
│   ├── groq_processor.py   # LLM translation/transliteration logic & pre-filtering
│   ├── translation_cache.py# Subdirectory caching for LLM responses
│   ├── sources/            # Lyrics source fetchers
│   │   ├── base_fetcher.py # Base class + shared utilities (build_result, parse_lrc)
│   │   ├── lrclib_fetcher.py
│   │   ├── genius_fetcher.py
│   │   ├── youtube_fetcher.py  # 3-layer: ytmusicapi → transcript-api → yt-dlp
│   │   ├── netease_fetcher.py
│   │   ├── megalobiz_fetcher.py
│   │   ├── musixmatch_fetcher.py
│   │   └── lrcmux_fetcher.py   # NEW: Musixmatch via api.lrcmux.dev; line & word-level sync
│   ├── sentiment_analyzer.py
│   ├── metadata_extractor.py
│   └── trending_analytics.py
├── Test/
│   └── lrcmux/
│       ├── run_test_and_log.py          # Integration test (line + word level)
│       └── test_fetcher_integration.py  # Unit-style fetcher assertions
├── .env.example
├── .lyrica.config.example
├── README.md
├── WORD_SYNC_GUIDE.md      # Word-level sync documentation (schema + implementation examples)
├── TRANSLATION_GUIDE.md    # Detailed guide on translation configuration
├── SETUP_GUIDE.md
└── requirements.txt
```

## Source Registry

| ID | Name | Fetcher file | Notes |
|----|------|-------------|-------|
| 1 | genius | `genius_fetcher.py` | Requires `GENIUS_TOKEN` |
| 2 | lrclib | `lrclib_fetcher.py` | Free, very reliable |
| 3 | youtube | `youtube_fetcher.py` | 3-layer fallback |
| 4 | netease | `netease_fetcher.py` | Via syncedlyrics |
| 5 | megalobiz | `megalobiz_fetcher.py` | Via syncedlyrics |
| 6 | musixmatch | `musixmatch_fetcher.py` | Via syncedlyrics, requires `MUSIXMATCH_TOKEN` |
| 7 | lrcmux | `lrcmux_fetcher.py` | Musixmatch via api.lrcmux.dev, no token needed |

**Default fallback order**: `lrclib → lrcmux → genius → youtube → netease → megalobiz → musixmatch`

## Key Query Parameters (`/lyrics/`)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `artist` | string | required | Artist name |
| `song` | string | required | Song title |
| `timestamps` | bool | false | Return line-level synced lyrics |
| `word` | bool | false | Return word-level synced lyrics (lrcmux only; requires `timestamps=true`) |
| `sequence` | string | all sources | Comma-separated source IDs or names (e.g. `2,7` or `lrclib,lrcmux`) |
| `fast` | bool | false | Parallel fetch mode |
| `mood` | bool | false | Sentiment analysis |
| `metadata` | bool | false | Cover art, genre, etc. |
| `translate` | bool | false | Translate lyrics via Groq LLM |
| `romanize` | bool | false | Romanize/transliterate via Groq LLM |
| `language` | string | en | Target language for translate/romanize |
| `pass` | bool | false | Only query sources in `sequence`, no fallback |

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `ADMIN_KEY` | Protects admin endpoints |
| `GENIUS_TOKEN` | Genius API auth |
| `MUSIXMATCH_TOKEN` | Musixmatch API auth |
| `GROQ_API_KEY` | Groq LLM key(s), comma-separated for load balancing |
| `GROQ_MODEL` | Override Groq model (default: `llama-3.3-70b-versatile`) |
| `PROXY_URL` | **Global proxy** for ALL fetchers; loaded into proxy pool at startup; comma-separated list supported |
| `YT_PROXY_URL` | YouTube-only proxy (handled inside `youtube_fetcher.py`) |
| `YT_COOKIES_PATH` | Absolute path to cookies.txt — takes priority over project root scan |
| `YT_HEADERS_PATH` | Absolute path to headers_auth.json — takes priority over project root scan |
| `LRCMUX_API_URL` | Override lrcmux base URL (default: `https://api.lrcmux.dev`) |
| `LRCLIB_API_URL` | Override lrclib base URL |
| `RATE_LIMIT_STORAGE_URI` | Rate limiter backend (default: `memory://`) |
| `LOG_LEVEL` | Logging level (default: `INFO`) |
| `CACHE_TTL` | Cache TTL in seconds (default: `86400`) |
| `CACHE_DIR` | Cache directory (default: `cache_data`) |

## Coding Rules

### 1. Async Pattern
- All new HTTP calls MUST use `httpx.AsyncClient`
- Use the `run_async()` helper in `router.py` to bridge sync Flask routes with async code
- Never use `requests` for new code (it's sync/blocking)

### 2. Response Shape
- All API responses follow: `{"status": "success"|"error", "data": {...}}` or `{"status": "error", "error": {"message": "...", "timestamp": "..."}}`
- Use `build_result()` from `base_fetcher.py` for fetcher results — extra kwargs go into the result dict via `**extra`
- Include ISO timestamps in all error responses

### 3. Cache Key Convention
- Cache keys are SHA-256 hashes of a JSON payload containing all relevant parameters
- Current `CACHE_VERSION = "v3"` in `cache.py` — bump when response format changes
- `word_level` is included in the cache key to prevent collisions between line and word sync responses
- Translation cache is separate from lyrics cache (different directory)

### 4. Config Hierarchy
- Query parameters ALWAYS override `.lyrica.config` values
- `.lyrica.config` values override hardcoded defaults
- Environment variables are for secrets and infrastructure config
- `PROXY_URL` env var seeds the proxy pool at `create_app()` time (before routes register)

### 5. Adding a New Fetcher
1. Create `src/sources/<name>_fetcher.py` — subclass `BaseFetcher`, implement `async fetch(artist, song, timestamps=False)`
2. Register in `src/sources/__init__.py` → `ALL_FETCHERS`
3. Add to `_SOURCE_ORDER` and `_SOURCE_BY_ID` in `src/fetch_controller.py`
4. Add `<name>_rpm` to `UserConfig` dataclass and `_load_from_path()` in `user_config.py`
5. If the fetcher needs a unique parameter (like `word_level` for lrcmux), handle it explicitly in `_try_fetcher()` in `fetch_controller.py`

### 6. Word-Level Sync Pattern (lrcmux-specific)
- `word_level` is a parameter only meaningful to lrcmux
- `fetch_controller._try_fetcher()` detects `source_name == "lrcmux"` and passes `word_level=word_level`
- Other fetchers receive only `timestamps` — do not add `word_level` to base `BaseFetcher.fetch()` signature
- When `timestamps=True, word_level=True` → `level=word` sent to lrcmux API
- When `timestamps=True, word_level=False` → `level=line` sent to lrcmux API
- `sync_level` from the API response `meta` dict is included in the result via `**extra`

### 7. Error Handling
- Fetchers must catch all exceptions and return `None` on failure (never crash the server)
- Log errors with `logger.error()`, warnings with `logger.warning()`
- Never expose internal stack traces to the API consumer

### 8. Security
- Never log or return API keys, tokens, or proxy credentials in API responses
- Admin endpoints require `ADMIN_KEY` via query param or `X-ADMIN-KEY` header
- Groq API keys are hash-masked in debug logs
- `PROXY_URL` is truncated to first 20 chars in startup log (`{url[:20]}***`)

### 9. Dependencies
- Prefer stdlib or already-installed packages over new dependencies
- Document any new dependency in `requirements.txt` with pinned version and comment

## Current Feature Roadmap

### Implemented (v1.4.0)
- Multi-source lyrics fetching — **7 sources** (Genius, LRCLIB, YouTube, NetEase, Megalobiz, Musixmatch, Lrcmux)
- Synced (timestamped) and plain lyrics
- **Word-Level Sync** — per-word timestamps via Lrcmux/Musixmatch (`&word=true&timestamps=true`)
- Mood/sentiment analysis
- Metadata enrichment (cover art, genre, etc.)
- Trending analytics by country
- JioSaavn search & stream
- Song suggestion via MusicBrainz
- File-based caching with TTL (`word_level` included in cache key)
- Proxy rotation — thread-safe pool; seedable via `PROXY_URL` env at startup
- User config file (`.lyrica.config`) with `word` default support
- Rate limiting
- **Lyrics Translation** — Translate lyrics via Groq LLM (`&translate=true&language=en`)
- **Lyrics Romanization** — Transliterate lyrics via Groq LLM (`&romanize=true&language=en`)
- Multi-key Groq API management with round-robin and 24h failover cooldowns
- YT auth via env vars (`YT_COOKIES_PATH`, `YT_HEADERS_PATH`) — priority over filesystem scan

### Planned (Future)
- Community translation database (contribute & share translations)
- Redis as alternative cache backend for translations
- WebSocket support for real-time lyric streaming
