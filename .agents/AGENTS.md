# Lyrica — Agent Rules & Project Conventions

## Project Overview

Lyrica is a high-performance **Python/Flask REST API** (v1.5.0) that aggregates song lyrics from multiple sources (Genius, LRCLIB, YouTube Music, NetEase, Megalobiz, Musixmatch, Lrcmux, Apple Music) with optional mood analysis, metadata enrichment, trending analytics, word-level and syllable-level sync, multi-tier Redis/memory/disk caching, and real-time lyrics translation/romanization via Groq LLM (`openai/gpt-oss-120b`).

## Tech Stack

- **Framework**: Flask 3.0+ (with async view support, threaded concurrency, and Vercel/Render/HF deployment compatibility)
- **HTTP Client**: `httpx` (async) with connection pooling (`max_connections=200`) — never `requests`
- **Serialization**: `orjson` (with stdlib `json` fallback)
- **HTML Parsing**: Fast regex and standard HTML decoding — never heavy `bs4` in runtime paths
- **Server**: Gunicorn (`gevent` / `gthread` for production), multi-threaded Flask dev server (local)
- **Python**: 3.11+
- **Config**: `.env` for secrets, `.lyrica.config` (INI format) for user preferences
- **Cache**: Multi-tier caching (`L1 Memory LRU` → `L2 Redis` → `L3 Disk JSON`)

## Architecture

```
lyrica/
├── run.py                  # Entry point (app instance & multi-threaded local runner)
├── pyproject.toml          # Python project & Vercel entrypoint config ([tool.vercel] entrypoint = "run:app")
├── vercel.json             # Vercel serverless routing configuration
├── gunicorn.config.py      # Production Gunicorn configuration (gevent / gthread concurrency)
├── src/
│   ├── __init__.py         # Package version (currently 1.5.0)
│   ├── app.py              # Flask app factory (create_app) + top-level app instance for Vercel
│   ├── router.py           # All route handlers
│   ├── config.py           # Environment variable loading (REDIS_URL, GROQ_MODEL, tokens)
│   ├── user_config.py      # .lyrica.config INI file parser
│   ├── cache.py            # Multi-tier caching system (L1 Memory LRU, L2 Redis, L3 Disk)
│   ├── fetch_controller.py # Orchestrates fetcher sequence & multi-sync-level fallback
│   ├── logger.py           # Centralized logging
│   ├── proxy_manager.py    # Thread-safe round-robin proxy pool singleton
│   ├── groq_key_manager.py # Groq API multi-key round-robin & cooldowns
│   ├── groq_processor.py   # LLM translation/transliteration logic via openai/gpt-oss-120b
│   ├── translation_cache.py# Multi-tier caching for translation responses
│   ├── sources/            # Lyrics source fetchers
│   │   ├── base_fetcher.py # Base class + shared httpx client with connection pooling
│   │   ├── lrclib_fetcher.py
│   │   ├── genius_fetcher.py  # Fast regex/HTML parser without bs4
│   │   ├── youtube_fetcher.py  # 3-layer: ytmusicapi → transcript-api → yt-dlp
│   │   ├── netease_fetcher.py
│   │   ├── megalobiz_fetcher.py
│   │   ├── musixmatch_fetcher.py
│   │   ├── lrcmux_fetcher.py   # Musixmatch via api.lrcmux.dev; line & word-level sync
│   │   └── apple_music_fetcher.py # Apple Music AMP API; line, word-level & syllable-level sync
│   ├── sentiment_analyzer.py
│   ├── metadata_extractor.py # Non-blocking async metadata aggregation (httpx + asyncio.gather)
│   └── trending_analytics.py # Apple Music RSS trending engine (httpx)
├── guide/
│   ├── SETUP_GUIDE.md        # Installation & setup guide
│   ├── USER_GUIDE.md         # Comprehensive API reference guide
│   ├── WORD_SYNC_GUIDE.md    # Word-level sync documentation (schema + implementation examples)
│   ├── TRANSLATION_GUIDE.md  # Detailed guide on translation configuration
│   └── DEPLOYMENT_GUIDE.md   # Deployment guide across Vercel, Docker, VPS, Render, HF, Railway, etc.
├── Test/
│   ├── test_production_upgrades.py      # Automated verification suite for cache, async, trending, routes
│   └── lrcmux/
│       ├── run_test_and_log.py          # Integration test (line + word level)
│       └── test_fetcher_integration.py  # Unit-style fetcher assertions
├── scripts/
│   └── parse_flask_routes.py # OpenAPI 3.0 route parser script
├── .env.example
├── .lyrica.config.example
├── README.md
├── openapi.json
└── requirements.txt
```

## Source Registry

| ID | Name | Fetcher file | Notes |
|----|------|-------------|-------|
| 1 | genius | `genius_fetcher.py` | Requires `GENIUS_TOKEN` (fast regex parser, no bs4) |
| 2 | lrclib | `lrclib_fetcher.py` | Free, very reliable |
| 3 | youtube | `youtube_fetcher.py` | 3-layer fallback |
| 4 | netease | `netease_fetcher.py` | Via syncedlyrics |
| 5 | megalobiz | `megalobiz_fetcher.py` | Via syncedlyrics |
| 6 | musixmatch | `musixmatch_fetcher.py` | Via syncedlyrics, requires `MUSIXMATCH_TOKEN` |
| 7 | lrcmux | `lrcmux_fetcher.py` | Musixmatch via api.lrcmux.dev, no token needed |
| 8 | apple_music | `apple_music_fetcher.py` | Apple Music AMP API, requires `APPLE_MUSIC_DEVELOPER_TOKEN` |

**Default fallback order**: `lrclib → lrcmux → genius → youtube → netease → megalobiz → musixmatch → apple_music`

## Key Query Parameters (`/lyrics/`)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `artist` | string | required | Artist name |
| `song` | string | required | Song title |
| `timestamps` | bool | false | Return line-level synced lyrics |
| `word` | bool | false | Return word-level synced lyrics (lrcmux or apple_music; requires `timestamps=true`) |
| `sequence` | string | all sources | Comma-separated source IDs or names (e.g. `2,7` or `lrclib,lrcmux`) |
| `fast` | bool | false | Parallel fetch mode |
| `mood` | bool | false | Sentiment analysis |
| `metadata` | bool | false | Cover art, genre, etc. |
| `translate` | bool | false | Translate lyrics via Groq LLM |
| `romanize` | bool | false | Romanize/transliterate via Groq LLM |
| `language` | string | en | Target language for translate/romanize |
| `pass` | bool | false | Only query sources in `sequence`, no fallback |
| `syllabus` | bool | false | Request syllable-level sync (Apple Music only; requires `timestamps=true` and `APPLE_MUSIC_DEVELOPER_TOKEN`) |

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `ADMIN_KEY` | Protects admin endpoints |
| `GENIUS_TOKEN` | Genius API auth |
| `MUSIXMATCH_TOKEN` | Musixmatch API auth |
| `APPLE_MUSIC_DEVELOPER_TOKEN` | Apple Music Developer JWT token (also accepts `DEVELOPER_TOKEN` alias) |
| `APPLE_MUSIC_USER_TOKEN` | Apple Music user token (also accepts `MUSIC_USER_TOKEN` alias) |
| `APPLE_STOREFRONT` | Apple Music storefront country code (default: `us`) |
| `APPLE_LYRICS_LANGUAGE` | Preferred lyrics language code (default: `en`) |
| `APPLE_LYRICS_SCRIPT` | Preferred lyrics script code (default: `latin`) |
| `GROQ_API_KEY` | Groq LLM key(s), comma-separated for load balancing |
| `GROQ_MODEL` | Override Groq model (default: `openai/gpt-oss-120b`) |
| `REDIS_URL` | Redis connection URL for L2 distributed cache and shared rate limiting |
| `PROXY_URL` | **Global proxy** for ALL fetchers; loaded into proxy pool at startup; comma-separated list supported |
| `YT_PROXY_URL` | YouTube-only proxy (handled inside `youtube_fetcher.py`) |
| `YT_COOKIES_PATH` | Absolute path to cookies.txt — takes priority over project root scan |
| `YT_HEADERS_PATH` | Absolute path to headers_auth.json — takes priority over project root scan |
| `LRCMUX_API_URL` | Override lrcmux base URL (default: `https://api.lrcmux.dev`) |
| `LRCLIB_API_URL` | Override lrclib base URL |
| `RATE_LIMIT_STORAGE_URI` | Rate limiter backend (defaults to `REDIS_URL` or `memory://`) |
| `LOG_LEVEL` | Logging level (default: `INFO`) |
| `CACHE_TTL` | Cache TTL in seconds (default: `86400`) |
| `CACHE_DIR` | Cache directory (default: `cache_data`) |

## Coding Rules

### 1. Async Pattern & No Blocking Calls
- All HTTP calls MUST use `httpx.AsyncClient` or shared connection pool
- Use the `run_async()` helper in `router.py` to bridge sync Flask routes with async code
- Never use `requests` or `bs4` anywhere in the codebase

### 2. Multi-Tier Caching System
- Tier 1: In-Memory LRU (microsecond response for hot items)
- Tier 2: Redis (`REDIS_URL`) with TTL and namespace isolation (`lyrica:lyrics:*`, `lyrica:trans:*`)
- Tier 3: Disk JSON (`cache_data/`) fallback
- Cache keys are SHA-256 hashes of JSON payload containing all relevant parameters (`CACHE_VERSION = "v5"`)

### 3. Response Shape
- All API responses follow: `{"status": "success"|"error", "data": {...}}` or `{"status": "error", "error": {"message": "...", "timestamp": "..."}}`
- Use `build_result()` from `base_fetcher.py` for fetcher results — extra kwargs go into the result dict via `**extra`
- Include ISO timestamps in all error responses

### 4. Config Hierarchy
- Query parameters ALWAYS override `.lyrica.config` values
- `.lyrica.config` values override hardcoded defaults
- Environment variables are for secrets and infrastructure config
- `PROXY_URL` env var seeds the proxy pool at `create_app()` time

### 5. Multi-Sync-Level Fallback Pattern
The `fetch_controller.py` implements a sync-level fallback hierarchy when `pass_param=False`:
1. **Syllable phase** (`&syllabus=true`): Tries `apple_music` with `syllabus=True, word_level=True`
2. **Word phase** (`&word=true`): Tries `lrcmux` + `apple_music` with `word_level=True`
3. **Line phase** (`&timestamps=true`): Tries all sources with line-level timing
4. **Plain phase** (`timestamps=false`): Tries all sources except `apple_music`

### 6. Security
- Never commit `.env`, `cookies.txt`, `headers_auth.json`, or any API keys/tokens
- Never log or return API keys, tokens, or proxy credentials in API responses
- Admin endpoints require `ADMIN_KEY` via query param or `X-ADMIN-KEY` header
- Groq API keys are hash-masked in debug logs
- `PROXY_URL` is truncated to first 20 chars in startup log (`{url[:20]}***`)
