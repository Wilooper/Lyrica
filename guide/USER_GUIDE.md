# 📖 Lyrica — Complete API & User Reference Guide

Welcome to the comprehensive API documentation for **Lyrica** (v1.4.0), a high-performance Python/Flask REST API for song lyrics, timestamps, word-level sync, metadata, sentiment analysis, trending analytics, and Groq-powered lyrics translation.

---

## 📌 Table of Contents

1. [Base URLs & Authentication](#base-urls--authentication)
2. [API Endpoint Reference](#api-endpoint-reference)
   - [`GET /lyrics/` — Main Lyrics Endpoint](#1-get-lyrics---main-lyrics-endpoint)
   - [`GET /metadata` — Song Metadata](#2-get-metadata---song-metadata)
   - [`GET /trending` — Trending Analytics](#3-get-trending---trending-analytics)
   - [`GET /analytics/*` — Metrics & Search Analytics](#4-get-analytics---metrics--search-analytics)
   - [`GET /suggestion` — Autocomplete & Search Suggestions](#5-get-suggestion---autocomplete--search-suggestions)
   - [`GET /jiosaavn/search` & `/jiosaavn/play` — JioSaavn Integration](#6-jiosaavn-search--stream)
   - [`GET /cache/stats` & `POST /cache/clear` — Cache Management](#7-cache-management)
   - [`GET /config` & `POST /config/reload` — Config Management](#8-config-management)
   - [`GET /proxy/stats` & `POST /proxy/reload` — Proxy Pool Admin](#9-proxy-pool-admin)
   - [`GET /openapi.json` — OpenAPI Specification](#10-openapi-specification)
   - [`GET /` & `/app` — Root & Web GUI](#11-root-info--web-gui)
3. [Lyrics Source Registry](#lyrics-source-registry)
4. [Error Codes & Responses](#error-codes--responses)
5. [Rate Limiting & Caching](#rate-limiting--caching)

---

## 🌐 Base URLs & Authentication

### Base URLs
- **Local Server**: `http://127.0.0.1:9999`
- **Hosted Instance (Render)**: `https://test-0k.onrender.com`
- **Hosted Instance (Hugging Face)**: `https://wilooper-lyrica.hf.space`

### Authentication
Public endpoints (lyrics search, trending, suggestions) require **no authentication**.
Admin endpoints (`/cache/clear`, `/config/reload`, `/proxy/reload`) require the `ADMIN_KEY`:

```bash
# Method 1: Query parameter
POST /cache/clear?key=YOUR_ADMIN_KEY

# Method 2: Request header
X-ADMIN-KEY: YOUR_ADMIN_KEY
```

---

## 🚀 API Endpoint Reference

### 1. `GET /lyrics/` — Main Lyrics Endpoint

Fetches lyrics from configured sources with optional timestamps, word-level sync, sentiment analysis, metadata, and Groq translation/romanization.

#### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `artist` | string | **Yes** | — | Artist name |
| `song` | string | **Yes** | — | Song title |
| `timestamps` | boolean | No | `false` | Return synchronized line-level LRC timestamps (`timed_lyrics`) |
| `word` | boolean | No | `false` | Return per-word synchronized timestamps via Lrcmux or Apple Music (`requires timestamps=true`) |
| `syllabus` | boolean | No | `false` | Return per-syllable synchronized timestamps via Apple Music (`requires timestamps=true`; requires `APPLE_MUSIC_DEVELOPER_TOKEN`) |
| `sequence` | string | No | — | Comma-separated fetcher IDs (e.g. `2,7,1` or `lrclib,lrcmux`) |
| `pass` | boolean | No | `false` | Restrict search strictly to sources in `sequence` without fallback |
| `fast` | boolean | No | `false` | Parallel fetching mode for fast response times |
| `mood` | boolean | No | `false` | Perform sentiment and word frequency analysis |
| `metadata` | boolean | No | `false` | Include cover art, album, release date, and duration |
| `translate` | boolean | No | `false` | Translate lyrics using Groq LLM |
| `romanize` | boolean | No | `false` | Romanize / transliterate lyrics using Groq LLM |
| `language` | string | No | `en` | Target language for translation/romanization |
| `country` | string | No | `US` | Country code for analytics tracking |

#### Example Requests

```bash
# Basic plain lyrics
curl "http://127.0.0.1:9999/lyrics/?artist=Coldplay&song=Yellow"

# Line-level synchronized timestamps
curl "http://127.0.0.1:9999/lyrics/?artist=Coldplay&song=Yellow&timestamps=true"

# Word-level synchronized timestamps (Karaoke)
# Word-Level Sync (Karaoke)
curl "http://127.0.0.1:9999/lyrics/?artist=Coldplay&song=Yellow&timestamps=true&word=true"

# Syllable-Level Sync (Apple Music)
curl "http://127.0.0.1:9999/lyrics/?artist=Coldplay&song=Yellow&timestamps=true&syllabus=true"

# Translated & Romanized synced lyrics
curl "http://127.0.0.1:9999/lyrics/?artist=Karan%20Aujla&song=Boyfriend&timestamps=true&translate=true&romanize=true&language=en"

# Fast Parallel Mode with Mood and Metadata
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho&fast=true&mood=true&metadata=true"
```

---

### 2. `GET /metadata` — Song Metadata

Retrieves standalone rich metadata for a track (cover art, artist, duration, album, release date).

```bash
curl "http://127.0.0.1:9999/metadata?artist=Taylor%20Swift&song=Blank%20Space"
```

---

### 3. `GET /trending` — Trending Analytics

Fetches real-time trending chart songs by country via Apple Music.

```bash
# Top 10 songs in India
curl "http://127.0.0.1:9999/trending/?country=IN&limit=10"

# Compare multiple countries
curl "http://127.0.0.1:9999/trending/?countries=US,IN,GB&limit=5"
```

---

### 4. `GET /analytics/*` — Metrics & Search Analytics

- `GET /analytics/top-queries?limit=10`: Most searched queries.
- `GET /analytics/trending-by-country`: Popular songs grouped by user query regions.
- `GET /analytics/trending-intersection`: Overlap between Apple Music trending charts and user searches.

---

### 5. `GET /suggestion` — Autocomplete & Search Suggestions

Provides instant song and artist autocomplete suggestions via MusicBrainz API.

```bash
curl "http://127.0.0.1:9999/suggestion?q=Tum%20Hi%20Ho&limit=5"
```

---

### 6. `GET /jiosaavn/search` & `/jiosaavn/play` — JioSaavn Integration

Allows Indian music search and direct audio stream retrieval via JioSaavn API.

```bash
# Search track
curl "http://127.0.0.1:9999/jiosaavn/search?query=Kesariya"

# Get direct stream link
curl "http://127.0.0.1:9999/jiosaavn/play?id=TRACK_ID"
```

---

### 7. Cache Management

- `GET /cache/stats`: View total cache size, hit counts, and disk usage.
- `POST /cache/clear?key=ADMIN_KEY`: Evict all cached items or clear specific patterns.

---

### 8. Config Management

- `GET /config`: Inspect active runtime configurations (`.lyrica.config` and environment variables).
- `POST /config/reload?key=ADMIN_KEY`: Hot-reload `.lyrica.config` without restarting the Flask process.

---

### 9. Proxy Pool Admin

- `GET /proxy/stats`: View active proxy pool count, health metrics, and failure counts.
- `POST /proxy/reload?key=ADMIN_KEY`: Force refresh and seed proxy list.

---

### 10. OpenAPI Specification

- `GET /openapi.json`: Returns the machine-readable OpenAPI 3.0 specification for Lyrica.

---

### 11. Root Info & Web GUI

- `GET /`: Returns API status, version (`1.4.0`), active endpoints, and health info.
- `GET /app`: Interactive HTML Web Interface to search lyrics, test translations, and view timed lyrics visually.

---

## 🎵 Lyrics Source Registry

| ID | Name | Source | Supported Sync | Auth Required |
|----|------|--------|----------------|---------------|
| 1 | `genius` | Genius.com | Plain | `GENIUS_TOKEN` (optional) |
| 2 | `lrclib` | LRCLIB | Line-level & Plain | None |
| 3 | `youtube` | YouTube Music | Line-level & Plain | None / Optional Cookies |
| 4 | `netease` | NetEase Cloud Music | Line-level (LRC) | None |
| 5 | `megalobiz` | Megalobiz | Line-level (LRC) | None |
| 6 | `musixmatch` | Musixmatch | Line-level (LRC) | `MUSIXMATCH_TOKEN` (optional) |
| 7 | `lrcmux` | Lrcmux (api.lrcmux.dev) | Line & Word-level | None |
| 8 | `apple_music` | Apple Music | Line, Word-level & Syllable-level | `APPLE_MUSIC_DEVELOPER_TOKEN` |

Default fallback sequence: `2 → 7 → 1 → 3 → 4 → 5 → 6 → 8`

---

## ❌ Error Codes & Responses

All API responses follow a uniform structure:

### Error Envelope
```json
{
  "status": "error",
  "error": {
    "message": "Lyrics not found for requested song",
    "timestamp": "2026-08-12T14:30:00Z"
  }
}
```

| HTTP Code | Description |
|-----------|-------------|
| `400 Bad Request` | Missing required parameters (`artist`, `song`) |
| `401 Unauthorized` | Invalid `ADMIN_KEY` provided for protected endpoint |
| `404 Not Found` | Lyrics not found across all attempted sources |
| `429 Too Many Requests` | IP rate limit exceeded (15 req/min default) |
| `503 Service Unavailable` | Groq translation requested but `GROQ_API_KEY` missing or unavailable |
