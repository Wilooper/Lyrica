# Lyrica — Agent Rules & Project Conventions

## Project Overview

Lyrica is a **Python/Flask REST API** that aggregates song lyrics from multiple sources (Genius, LRCLIB, YouTube Music, NetEase, Megalobiz, Musixmatch) with optional mood analysis, metadata enrichment, trending analytics, and lyrics translation/romanization via Groq LLM.

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
│   ├── app.py              # Flask app factory (create_app)
│   ├── router.py           # All route handlers
│   ├── config.py           # Environment variable loading
│   ├── user_config.py      # .lyrica.config INI file parser
│   ├── cache.py            # File-based caching system
│   ├── fetch_controller.py # Orchestrates fetcher sequence
│   ├── logger.py           # Centralized logging
│   ├── groq_key_manager.py # Groq API multi-key round-robin & cooldowns
│   ├── groq_processor.py   # LLM translation/transliteration logic & pre-filtering
│   ├── translation_cache.py# Subdirectory caching for LLM responses
│   ├── sources/            # Lyrics source fetchers
│   │   ├── base_fetcher.py # Base class + shared utilities
│   │   ├── lrclib_fetcher.py
│   │   ├── genius_fetcher.py
│   │   ├── youtube_fetcher.py
│   │   └── ...
│   ├── sentiment_analyzer.py
│   ├── metadata_extractor.py
│   └── trending_analytics.py
├── .env.example
├── .lyrica.config.example
├── TRANSLATION_GUIDE.md    # Detailed guide on translation configuration
└── requirements.txt
```

## Coding Rules

### 1. Async Pattern
- All new HTTP calls MUST use `httpx.AsyncClient`
- Use the `run_async()` helper in `router.py` to bridge sync Flask routes with async code
- Never use `requests` for new code (it's sync/blocking)

### 2. Response Shape
- All API responses follow: `{"status": "success"|"error", "data": {...}}` or `{"status": "error", "error": {"message": "...", "timestamp": "..."}}`
- Use `build_result()` from `base_fetcher.py` for fetcher results
- Include ISO timestamps in all error responses

### 3. Cache Key Convention
- Cache keys are SHA-256 hashes of a JSON payload containing all relevant parameters
- Bump `CACHE_VERSION` when response format changes
- Translation cache is separate from lyrics cache (different directory)

### 4. Config Hierarchy
- Query parameters ALWAYS override `.lyrica.config` values
- `.lyrica.config` values override hardcoded defaults
- Environment variables are for secrets and infrastructure config

### 5. Error Handling
- Fetchers must catch all exceptions and return `None` on failure (never crash the server)
- Log errors with `logger.error()`, warnings with `logger.warning()`
- Never expose internal stack traces to the API consumer

### 6. Security
- Never log or return API keys, tokens, or proxy credentials in API responses
- Admin endpoints require `ADMIN_KEY` via query param or `X-ADMIN-KEY` header
- Groq API keys are hash-masked in debug logs

### 7. Dependencies
- Prefer stdlib or already-installed packages over new dependencies
- Document any new dependency in `requirements.txt` with pinned version and comment

## Current Feature Roadmap

### Implemented
- Multi-source lyrics fetching (6 sources)
- Synced (timestamped) and plain lyrics
- Mood/sentiment analysis
- Metadata enrichment (cover art, genre, etc.)
- Trending analytics by country
- JioSaavn search & stream
- Song suggestion via MusicBrainz
- File-based caching with TTL
- Proxy rotation
- User config file (`.lyrica.config`)
- Rate limiting
- **Lyrics Translation** — Translate lyrics via Groq LLM (`&translate=true&language=en`)
- **Lyrics Romanization** — Transliterate lyrics via Groq LLM (`&romanize=true&language=en`)
- Multi-key Groq API management with round-robin and 24h failover cooldowns

### In Progress

### Planned (Future)
- Community translation database (contribute & share translations)
- Redis as alternative cache backend for translations
- WebSocket support for real-time lyric streaming
