# Lyrica - Complete User Guide & API Reference

## Table of Contents

1. [Getting Started](#getting-started)
2. [API Endpoints](#api-endpoints)
   - [Lyrics](#1-lyrics-endpoint-main)
   - [Metadata](#2-metadata-endpoint)
   - [Trending](#3-trending-endpoint)
   - [Analytics - Top Queries](#4-analytics---top-queries)
   - [Analytics - Trending by Country](#5-analytics---trending-by-country)
   - [Analytics - Trending vs Queries](#6-analytics---trending-vs-queries)
   - [Analytics - Trending Intersection](#7-analytics---trending-intersection)
   - [Song Suggestion / Autocomplete](#8-song-suggestion--autocomplete)
   - [JioSaavn Search](#9-jiosaavn-search)
   - [JioSaavn Play](#10-jiosaavn-play)
   - [Cache Statistics](#11-cache-statistics)
   - [Cache Clear (Admin)](#12-cache-clear-admin)
   - [Health Check](#13-health-check)
   - [Proxy Rotation Pools (Admin)](#14-proxy-rotation-pools-admin)
   - [Configuration Management (Admin)](#15-configuration-management-admin)
   - [Web GUI](#16-web-gui)
   - [API Info](#17-api-info)
3. [Core Features](#core-features)
4. [Source Reference](#source-reference)
5. [Response Formats](#response-formats)
6. [Error Handling](#error-handling)
7. [Best Practices](#best-practices)
8. [Code Examples](#code-examples)
9. [Installation & Configuration Reference](#installation--configuration-reference)
10. [FAQ](#frequently-asked-questions)

---

## Getting Started

### Base URLs

- **Local Development**: `http://127.0.0.1:9999`
- **Production Demo**: `https://test-0k.onrender.com`
- **Production (High Traffic)**: `https://wilooper-lyrica.hf.space`
- **API Info**: `/` (root endpoint)
- **Web GUI**: `/app`

### Authentication

Lyrica does not require authentication for public endpoints. Admin endpoints require an `ADMIN_KEY`:

```bash
# Method 1: Query parameter
POST /cache/clear?key=your_admin_key

# Method 2: Request header
X-ADMIN-KEY: your_admin_key
```

---

## API Endpoints

### 1. Lyrics Endpoint (Main)

**Retrieve lyrics with optional mood analysis, timestamps, and metadata**

```
GET /lyrics/
```

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `artist` | string | Yes | — | Artist name (e.g., `"Arijit Singh"`) |
| `song` | string | Yes | — | Song title (e.g., `"Tum Hi Ho"`) |
| `timestamps` | boolean | No | false | Include synchronized LRC timestamps |
| `mood` | boolean | No | false | Include sentiment & word frequency analysis |
| `metadata` | boolean | No | false | Include song metadata (cover art, duration, genre) |
| `fast` | boolean | No | false | Parallel fetching across best sources |
| `pass` | boolean | No | false | Enable custom fetcher sequence |
| `sequence` | string | No | — | Comma-separated fetcher IDs (e.g., `"1,3,5"`). Requires `pass=true` |
| `country` | string | No | US | Country code for query analytics recording (e.g., `IN`, `GB`) |

#### Source IDs

| ID | Source | Lyrics Type |
|----|--------|-------------|
| 1 | Genius | Plain (requires `GENIUS_TOKEN`) |
| 2 | LRCLIB | Timestamped + Plain |
| 3 | YouTube Music | Timestamped + Plain |
| 4 | NetEase | Timestamped (LRC) |
| 5 | Megalobiz | Timestamped (LRC) |
| 6 | Musixmatch | Timestamped (LRC) |
| 7 | SimpMusic | Timestamped + Plain |

**Default Sequences:**
- Plain lyrics: `[1, 2, 3, 4, 5, 6, 7]`
- With timestamps: `[2, 3, 4, 5, 6, 7]`
- Fast mode: `[2, 3]` (LRCLIB + YouTube Music, parallel)

#### Example Requests

**Basic Request**
```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho"
```

**With Timestamps**
```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho&timestamps=true"
```

**With Mood Analysis**
```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho&mood=true"
```

**With Metadata**
```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho&metadata=true"
```

**Custom Source Sequence**
```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho&pass=true&sequence=2,3,4"
```

**Fast Mode (All Features)**
```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho&fast=true&timestamps=true&mood=true&metadata=true"
```

#### Success Response (200 OK)

**Plain Lyrics:**
```json
{
  "status": "success",
  "data": {
    "source": "genius",
    "artist": "Arijit Singh",
    "title": "Tum Hi Ho",
    "plain_lyrics": "Hum tere bin ab reh nahi sakte\nTere bina kya wajood mera...",
    "lyrics": "Hum tere bin ab reh nahi sakte\nTere bina kya wajood mera...",
    "timestamp": "2026-06-24T12:20:00+00:00"
  },
  "attempts": [
    {
      "api": "lrclib",
      "status": "no_lyrics"
    }
  ]
}
```

**With Timestamps:**
```json
{
  "status": "success",
  "data": {
    "source": "youtube_music",
    "artist": "Arijit Singh",
    "title": "Tum Hi Ho",
    "plain_lyrics": "Hum tere bin ab reh nahi sakte...",
    "lyrics": "Hum tere bin ab reh nahi sakte...",
    "timed_lyrics": [
      {
        "text": "Hum tere bin ab reh nahi sakte",
        "start_time": 0,
        "end_time": 5200,
        "id": 1
      },
      {
        "text": "Tere bina kya wajood mera",
        "start_time": 5200,
        "end_time": 10400,
        "id": 2
      }
    ],
    "hasTimestamps": true,
    "timestamp": "2026-06-24T12:20:00+00:00"
  },
  "attempts": []
}
```

**With Mood Analysis:**
```json
{
  "status": "success",
  "data": {
    "source": "genius",
    "artist": "Arijit Singh",
    "title": "Tum Hi Ho",
    "lyrics": "..."
  },
  "mood_analysis": {
    "sentiment": {
      "polarity": -0.45,
      "subjectivity": 0.75,
      "emotion": "sad",
      "confidence": 0.87
    },
    "top_words": [
      {"word": "love", "frequency": 12},
      {"word": "heart", "frequency": 8},
      {"word": "night", "frequency": 7}
    ]
  }
}
```

**With Metadata:**
```json
{
  "status": "success",
  "data": {
    "source": "genius",
    "artist": "Arijit Singh",
    "title": "Tum Hi Ho",
    "lyrics": "...",
    "metadata": {
      "cover_art": "https://example.com/cover.jpg",
      "duration": "4:30",
      "genre": "Bollywood, Romance",
      "release_date": "2013-01-15",
      "album": "Aashiqui 2",
      "explicit": false
    }
  }
}
```

#### Error Responses

**Missing Parameters (400)**
```json
{
  "status": "error",
  "error": {
    "message": "Artist and song name are required",
    "timestamp": "2026-06-24T12:20:00+00:00"
  }
}
```

**No Lyrics Found (from error message)**
```json
{
  "status": "error",
  "error": {
    "message": "No lyrics found for 'XYZ' by 'Unknown Artist'",
    "timestamp": "2026-06-24T12:20:00+00:00"
  }
}
```

**Request Timeout (504)**
```json
{
  "status": "error",
  "error": {
    "message": "Request timed out",
    "details": "Lyrics fetch took too long",
    "timestamp": "2026-06-24T12:20:00+00:00"
  }
}
```

**Rate Limit Exceeded (429)**
```json
{
  "status": "error",
  "error": {
    "message": "Rate limit exceeded. Please wait before retrying.",
    "retry_after": 45
  }
}
```

---

### 2. Metadata Endpoint

**Get song metadata without lyrics**

```
GET /metadata/
```

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `artist` | string | Yes | Artist name |
| `song` | string | Yes | Song title |

#### Example Request

```bash
curl "http://127.0.0.1:9999/metadata/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho"
```

#### Response

```json
{
  "status": "success",
  "data": {
    "cover_art": "https://example.com/cover.jpg",
    "duration": "4:30",
    "genre": "Bollywood, Romance",
    "release_date": "2013-01-15",
    "album": "Aashiqui 2",
    "artist": "Arijit Singh",
    "title": "Tum Hi Ho",
    "explicit": false,
    "producer": "Mithoon",
    "writer": "Mithoon"
  }
}
```

---

### 3. Trending Endpoint

**Get trending songs by country using Apple Music data**

```
GET /trending/
```

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `country` | string | No | US | Country code (e.g., `US`, `IN`, `GB`, `JP`, `DE`, `FR`, `BR`, `CA`, `AU`, `MX`) |
| `countries` | string | No | — | Comma-separated country codes for multi-country response (e.g., `US,IN,GB`) |
| `limit` | integer | No | 20 | Number of trending songs (1–100) |

#### Example Requests

**Single Country**
```bash
curl "http://127.0.0.1:9999/trending/?country=IN&limit=10"
```

**Multiple Countries**
```bash
curl "http://127.0.0.1:9999/trending/?countries=US,IN,GB&limit=5"
```

#### Response (Single Country)

```json
{
  "status": "success",
  "data": {
    "country": "IN",
    "trending": [
      {
        "title": "Kesariya",
        "artist": "Arijit Singh",
        "rank": 1,
        "album": "Brahmastra",
        "cover_art": "https://example.com/cover.jpg"
      }
    ],
    "total": 10,
    "timestamp": "2026-06-24T12:20:00+00:00"
  }
}
```

#### Response (Multiple Countries)

```json
{
  "status": "success",
  "data": {
    "countries": {
      "US": [ { "title": "...", "artist": "..." } ],
      "IN": [ { "title": "...", "artist": "..." } ],
      "GB": [ { "title": "...", "artist": "..." } ]
    },
    "timestamp": "2026-06-24T12:20:00+00:00"
  }
}
```

**Valid Country Codes:** `US`, `GB`, `IN`, `BR`, `JP`, `DE`, `FR`, `CA`, `AU`, `MX`

---

### 4. Analytics - Top Queries

**Get the most searched songs on your server**

```
GET /analytics/top-queries/
```

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `limit` | integer | No | 20 | Number of results (1–100) |
| `country` | string | No | — | Filter by country code |
| `days` | integer | No | — | Time window in days (omit for all-time) |

#### Example Requests

```bash
# Global top 20 all-time
curl "http://127.0.0.1:9999/analytics/top-queries/?limit=20"

# US top 10 from the last 7 days
curl "http://127.0.0.1:9999/analytics/top-queries/?country=US&days=7&limit=10"
```

#### Response

```json
{
  "status": "success",
  "data": {
    "scope": "global",
    "time_window": "all_time",
    "top_queries": [
      {"query": "Arijit Singh - Tum Hi Ho", "count": 154},
      {"query": "The Weeknd - Blinding Lights", "count": 98}
    ],
    "total_unique": 2,
    "timestamp": "2026-06-24T12:20:00+00:00"
  }
}
```

---

### 5. Analytics - Trending by Country

**Get top user queries for each country**

```
GET /analytics/trending-by-country/
```

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `limit` | integer | No | 10 | Number of queries per country (1–100) |

#### Example Request

```bash
curl "http://127.0.0.1:9999/analytics/trending-by-country/?limit=5"
```

#### Response

```json
{
  "status": "success",
  "data": {
    "countries": {
      "IN": [
        {"query": "Arijit Singh - Tum Hi Ho", "count": 45}
      ],
      "US": [
        {"query": "The Weeknd - Blinding Lights", "count": 30}
      ]
    },
    "total_countries": 2,
    "timestamp": "2026-06-24T12:20:00+00:00"
  }
}
```

---

### 6. Analytics - Trending vs Queries

**Compare Apple Music trending songs with user query data for a country**

```
GET /analytics/trending-vs-queries/
```

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `country` | string | No | US | Country code |
| `limit` | integer | No | 10 | Number of results |

#### Example Request

```bash
curl "http://127.0.0.1:9999/analytics/trending-vs-queries/?country=IN&limit=10"
```

#### Response

```json
{
  "status": "success",
  "data": {
    "trending": [...],
    "top_queries": [...]
  }
}
```

---

### 7. Analytics - Trending Intersection

**Find user queries that match currently trending songs**

```
GET /analytics/trending-intersection/
```

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `country` | string | No | US | Country code |
| `limit` | integer | No | 10 | Maximum results |

#### Example Request

```bash
curl "http://127.0.0.1:9999/analytics/trending-intersection/?country=US&limit=10"
```

#### Response

```json
{
  "status": "success",
  "data": {
    "country": "US",
    "matches": [
      {"query": "Taylor Swift - Shake It Off", "trending_rank": 3, "query_count": 22}
    ],
    "total_matches": 1,
    "timestamp": "2026-06-24T12:20:00+00:00"
  }
}
```

---

### 8. Song Suggestion / Autocomplete

**Search for songs by name and return matching titles with artists (powered by MusicBrainz)**

```
GET /suggestion
```

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `q` | string | Yes | — | Search query |
| `limit` | integer | No | 10 | Number of results (1–100) |

#### Example Request

```bash
curl "http://127.0.0.1:9999/suggestion?q=Tum%20Hi%20Ho&limit=5"
```

#### Response

```json
{
  "status": "success",
  "query": "Tum Hi Ho",
  "limit": 5,
  "total": 3,
  "results": [
    {"title": "Tum Hi Ho", "artist": "Arijit Singh"},
    {"title": "Tum Hi Ho (Reprise)", "artist": "Arijit Singh"},
    {"title": "Tum Hi Ho (Cover)", "artist": "Various"}
  ]
}
```

---

### 9. JioSaavn Search

**Search for songs on JioSaavn**

```
GET /api/jiosaavn/search
```

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `q` | string | Yes | Search query (song name, artist, etc.) |

#### Example Request

```bash
curl "http://127.0.0.1:9999/api/jiosaavn/search?q=Tum%20Hi%20Ho"
```

#### Response

```json
{
  "status": "success",
  "results": [
    {
      "id": "song_123",
      "title": "Tum Hi Ho",
      "artist": "Arijit Singh",
      "album": "Aashiqui 2",
      "duration": 270,
      "image": "https://example.com/image.jpg",
      "song_link": "https://jiosaavn.com/song/xyz"
    }
  ]
}
```

---

### 10. JioSaavn Play

**Get a playable stream URL from JioSaavn**

```
GET /api/jiosaavn/play
```

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `songLink` | string | Yes | Song link from JioSaavn search results |

#### Example Request

```bash
curl "http://127.0.0.1:9999/api/jiosaavn/play?songLink=https://jiosaavn.com/song/xyz"
```

#### Response

```json
{
  "status": "success",
  "data": {
    "stream_url": "https://streaming.jiosaavn.com/audio/xyz.mp3",
    "quality": "320kbps",
    "duration": 270,
    "title": "Tum Hi Ho",
    "artist": "Arijit Singh"
  }
}
```

---

### 11. Cache Statistics

**Get cache hit/miss statistics**

```
GET /cache/stats
```

#### Example Request

```bash
curl "http://127.0.0.1:9999/cache/stats"
```

#### Response

```json
{
  "status": "success",
  "hits": 250,
  "misses": 85,
  "total_entries": 150,
  "hit_rate": "74.6%",
  "timestamp": "2026-06-24T12:20:00+00:00"
}
```

---

### 12. Cache Clear (Admin)

**Clear all cached data — requires `ADMIN_KEY`**

```
POST /cache/clear
```

#### Authentication

Pass your admin key via query parameter or header:

```bash
# Query parameter
curl -X POST "http://127.0.0.1:9999/cache/clear?key=your_admin_key"

# Header
curl -X POST http://127.0.0.1:9999/cache/clear \
  -H "X-ADMIN-KEY: your_admin_key"
```

#### Response

```json
{
  "status": "success",
  "details": {
    "cleared": 150,
    "timestamp": "2026-06-24T12:20:00+00:00"
  }
}
```

#### Error (403 Forbidden)

```json
{
  "status": "error",
  "error": {
    "message": "Unauthorized"
  }
}
```

---

### 13. Health Check

**Monitor the API status, loaded version, and system timestamp**

```
GET /health
```

#### Example Request
```bash
curl "http://127.0.0.1:9999/health"
```

#### Response
```json
{
  "status": "ok",
  "version": "1.3.0",
  "timestamp": "2026-07-19T16:20:00+00:00"
}
```

---

### 14. Proxy Rotation Pools (Admin)

**Manage the active round-robin proxy pool — requires `ADMIN_KEY`**

#### 14.1 Add Proxy
```
POST /v2/proxy/set
```
**JSON body or Query parameters:**
- `proxy`: Proxy connection string (e.g. `http://user:pass@host:port` or `socks5://host:port`)
- `key` (or header `X-ADMIN-KEY`): Admin key

**Example:**
```bash
curl -X POST "http://127.0.0.1:9999/v2/proxy/set?key=your_admin_key" \
  -H "Content-Type: application/json" \
  -d '{"proxy": "http://myproxy.com:8080"}'
```

#### 14.2 Remove Proxy
```
DELETE /v2/proxy/remove
```
**JSON body or Query parameters:**
- `proxy`: The proxy string to remove

**Example:**
```bash
curl -X DELETE "http://127.0.0.1:9999/v2/proxy/remove?key=your_admin_key" \
  -H "Content-Type: application/json" \
  -d '{"proxy": "http://myproxy.com:8080"}'
```

#### 14.3 List Proxies
```
GET /v2/proxy/list
```
Returns loaded proxies with credentials masked for safety.

**Example:**
```bash
curl "http://127.0.0.1:9999/v2/proxy/list?key=your_admin_key"
```

#### 14.4 Clear Proxy Pool
```
POST /v2/proxy/clear
```
Removes all proxies from memory.

**Example:**
```bash
curl -X POST "http://127.0.0.1:9999/v2/proxy/clear?key=your_admin_key"
```

---

### 15. Configuration Management (Admin)

**View and hot-reload config values dynamically — requires `ADMIN_KEY`**

#### 15.1 View Config Status
```
GET /config/status
```
Returns currently loaded config file path and active values.

**Example:**
```bash
curl "http://127.0.0.1:9999/config/status"
```

#### 15.2 Force Config Reload
```
POST /config/reload
```
Force re-reads `.lyrica.config` from disk without restarting the application.

**Example:**
```bash
curl -X POST "http://127.0.0.1:9999/config/reload?key=your_admin_key"
```

#### Response
```json
{
  "status": "success",
  "message": "Config reloaded",
  "config": {
    "config_path": "/path/to/.lyrica.config",
    "defaults": {
      "fast": false,
      "metadata": false,
      "mood": false,
      "sequence": "1,2,3",
      "timestamps": false
    },
    "server": {
      "fast_timeout": 20,
      "request_timeout": 60
    }
  },
  "timestamp": "2026-07-19T16:20:00+00:00"
}
```


### 16. Web GUI

**Interactive web interface for testing**

```
GET /app
```

Navigate to `http://127.0.0.1:9999/app` in your browser to use the built-in GUI.

---

### 17. API Info

**Get API version, status, and endpoint summary**

```
GET /
```

Returns a JSON object listing all endpoints, parameters, and active fetchers.

---

## Core Features

### Timestamped Lyrics (LRC Format)

Get lyrics synchronized with millisecond precision — perfect for karaoke-style displays.

```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho&timestamps=true"
```

**Response includes `timed_lyrics` array:**
```json
{
  "timed_lyrics": [
    {"text": "Hum tere bin ab reh nahi sakte", "start_time": 0, "end_time": 5200, "id": 1},
    {"text": "Tere bina kya wajood mera", "start_time": 5200, "end_time": 10400, "id": 2}
  ],
  "hasTimestamps": true
}
```

**Sources that provide timestamps:** LRCLIB (2), YouTube Music (3), NetEase (4), Megalobiz (5), Musixmatch (6), SimpMusic (7)

---

### Mood & Sentiment Analysis

Understand the emotional tone of a song's lyrics.

```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho&mood=true"
```

**Analysis includes:**
- **Polarity**: −1 (very negative) to +1 (very positive)
- **Subjectivity**: 0 (objective) to 1 (highly subjective)
- **Emotion**: `sad`, `happy`, `energetic`, `calm`, `romantic`, etc.
- **Top Words**: Most frequently used meaningful words

---

### Rich Metadata

Get comprehensive song information alongside lyrics.

```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho&metadata=true"
```

**Metadata includes:** album artwork, duration, genre, release date, album name, producer/writer credits, explicit content flag.

---

### Fast Mode (Parallel Fetching)

Race the two best synced sources (LRCLIB + YouTube Music) simultaneously — first valid result wins.

```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho&fast=true"
```

**Performance:**
- Default sequential: ~500–2000 ms
- Fast Mode: ~300–800 ms
- With caching: < 50 ms

---

### Custom Source Sequencing

Control which sources to query and in what order.

```bash
# Only synced sources
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho&pass=true&sequence=2,4,5"

# Prioritise Genius + YouTube
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho&pass=true&sequence=1,3"
```

When more than one ID is supplied with `pass=true`, all fetchers run **in parallel** and the first validated result wins.

---

### Intelligent Caching

Reduce redundant external calls with file-based TTL caching.

```bash
# View stats
curl "http://127.0.0.1:9999/cache/stats"

# Clear cache (admin)
curl -X POST "http://127.0.0.1:9999/cache/clear?key=your_admin_key"
```

---

## Source Reference

| ID | Name | Type | Notes |
|----|------|------|-------|
| 1 | Genius | Plain | Requires `GENIUS_TOKEN` env var |
| 2 | LRCLIB | Timestamped + Plain | Free, no auth needed, highly reliable |
| 3 | YouTube Music | Timestamped + Plain | 3-layer: ytmusicapi → transcript-api → yt-dlp |
| 4 | NetEase | Timestamped (LRC) | Via `syncedlyrics`, large global catalog |
| 5 | Megalobiz | Timestamped (LRC) | Via `syncedlyrics`, user-contributed |
| 6 | Musixmatch | Timestamped (LRC) | Via `syncedlyrics`, optional `MUSIXMATCH_TOKEN` |
| 7 | SimpMusic | Timestamped + Plain | Via api-lyrics.simpmusic.org |

> **Note:** Lyrics.ovh, ChartLyrics, and LyricsFreek have been removed — their APIs are dead as of June 2026.

---

## Response Formats

### Standard Response Structure

```json
{
  "status": "success | error",
  "data": {
    // Response-specific payload
  },
  "error": {
    // Only present when status == "error"
    "message": "Human-readable error message",
    "details": "Optional additional info",
    "timestamp": "ISO 8601 timestamp"
  },
  "attempts": [
    // Only in /lyrics/ — shows fallback attempt log
    {
      "api": "source_name",
      "status": "no_lyrics | validation_failed | error | not_configured",
      "reason": "Optional reason string"
    }
  ]
}
```

---

## Error Handling

### HTTP Status Codes

| Code | Meaning | Example |
|------|---------|---------|
| 200 | Success | Lyrics found and returned |
| 400 | Bad Request | Missing required parameters or invalid sequence |
| 403 | Forbidden | Invalid or missing admin key |
| 404 | Not Found | Endpoint does not exist |
| 429 | Rate Limited | Too many requests |
| 500 | Server Error | Internal processing error |
| 504 | Gateway Timeout | Fetch took too long |

### Common Errors and Solutions

**"Artist and song name are required"**
```
Cause: Missing artist or song parameter
Solution: Include both ?artist=X&song=Y in request
```

**"No lyrics found for '...'"**
```
Cause: No source returned valid lyrics for that query
Solution: Check spelling, try exact artist/title, try popular songs first
```

**"Invalid sequence format"**
```
Cause: Non-integer values in sequence string
Solution: Use comma-separated integers, e.g. sequence=1,3,4
```

**"Rate limit exceeded"**
```
Cause: > 15 requests/minute from your IP
Solution: Cache results client-side, wait for the window to reset
```

**"Request timed out"**
```
Cause: Sources took too long to respond
Solution: Use fast=true, or try with a shorter custom sequence
```

---

## Best Practices

### 1. URL-Encode Parameters

```bash
# Correct
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho"

# Incorrect (spaces break the query)
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit Singh&song=Tum Hi Ho"
```

### 2. Batch Options into One Request

```bash
# Instead of three separate requests, use one:
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho&timestamps=true&mood=true&metadata=true&fast=true"
```

### 3. Always Check Status

```javascript
if (response.data.status === 'error') {
  console.error(response.data.error.message);
  // Handle gracefully in your UI
}
```

### 4. Cache Results Client-Side

Store API responses in your app for 1–2 minutes to stay within rate limits and reduce latency.

### 5. Choose Sequences for Your Use Case

```bash
# Speed-first (parallel, synced only)
fast=true

# Quality-first (Genius + YouTube)
pass=true&sequence=1,3

# Synced lyrics only
pass=true&sequence=2,3,4,5,6,7

# Lightweight / low-bandwidth
pass=true&sequence=2,4
```

---

## Code Examples

### JavaScript / Fetch API

```javascript
async function getLyrics(artist, song, options = {}) {
  const params = new URLSearchParams({
    artist,
    song,
    timestamps: options.timestamps || false,
    mood:       options.mood       || false,
    metadata:   options.metadata   || false,
    fast:       options.fast       || false
  });

  const response = await fetch(`http://127.0.0.1:9999/lyrics/?${params}`);
  const data = await response.json();

  if (data.status === 'success') {
    return {
      lyrics:      data.data.lyrics,
      source:      data.data.source,
      mood:        data.mood_analysis  || null,
      metadata:    data.data.metadata  || null,
      timedLyrics: data.data.timed_lyrics || null
    };
  } else {
    throw new Error(data.error.message);
  }
}

// Usage
getLyrics('Arijit Singh', 'Tum Hi Ho', {
  timestamps: true, mood: true, metadata: true, fast: true
}).then(console.log).catch(console.error);
```

### Python / Requests

```python
import requests

def get_lyrics(artist, song, **options):
    params = {
        'artist':     artist,
        'song':       song,
        'timestamps': options.get('timestamps', False),
        'mood':       options.get('mood', False),
        'metadata':   options.get('metadata', False),
        'fast':       options.get('fast', False),
    }
    response = requests.get('http://127.0.0.1:9999/lyrics/', params=params)
    data = response.json()

    if data['status'] == 'success':
        return {
            'lyrics':   data['data']['lyrics'],
            'source':   data['data']['source'],
            'mood':     data.get('mood_analysis'),
            'metadata': data['data'].get('metadata'),
        }
    else:
        raise Exception(data['error']['message'])

# Usage
try:
    result = get_lyrics('Arijit Singh', 'Tum Hi Ho', timestamps=True, fast=True)
    print(result)
except Exception as e:
    print(f"Error: {e}")
```

### Trending Example (Python)

```python
import requests

# Get top 10 trending in India
r = requests.get('http://127.0.0.1:9999/trending/', params={'country': 'IN', 'limit': 10})
data = r.json()
for song in data['data']['trending']:
    print(f"{song.get('rank', '?')}. {song['title']} — {song['artist']}")
```

### cURL

```bash
#!/bin/bash
ARTIST="Arijit Singh"
SONG="Tum Hi Ho"
API_URL="http://127.0.0.1:9999"

# Fetch with all features
curl "${API_URL}/lyrics/?artist=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$ARTIST'))")&song=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$SONG'))")&fast=true&timestamps=true&mood=true&metadata=true"
```

---

## Installation & Configuration Reference

### Full Setup Checklist

- [ ] Python 3.12+ installed
- [ ] Clone repository: `git clone https://github.com/Wilooper/Lyrica.git`
- [ ] Create virtual environment: `python -m venv venv`
- [ ] Activate environment: `source venv/bin/activate` (Windows: `venv\Scripts\activate`)
- [ ] Install dependencies: `pip install -r requirements.txt`
- [ ] Copy env file: `cp .env.example .env` and fill in values
- [ ] Run server: `python run.py`
- [ ] Test API: `curl http://127.0.0.1:9999/`
- [ ] Access GUI: `http://127.0.0.1:9999/app`

### Obtaining API Keys

**Genius API Token (Optional but recommended for source 1):**
1. Visit https://genius.com/api-clients
2. Create account / log in
3. Create a new API Client
4. Copy the Client Access Token
5. Add to `.env`: `GENIUS_TOKEN=your_token`

**Proxy Rotation Pool (Optional):**
- To set up proxy rotation for robust fetching under rate limits, copy `.lyrica.config.example` to `.lyrica.config` and add proxies under the `[proxies]` section.
- You can add both HTTP and SOCKS5 proxies. Credentials will be auto-masked in all API responses.

**Musixmatch Token (Optional):**
- Register at https://developer.musixmatch.com/
- Add `MUSIXMATCH_TOKEN=your_token` to `.env`

---

## Frequently Asked Questions

**Q: Is authentication required?**
A: No — public endpoints work without any key. Only administrative endpoints (like `/cache/clear`, `/config/reload`, `/v2/proxy/*`) require the `ADMIN_KEY`.

**Q: What's the rate limit?**
A: 15 requests/minute per IP by default. Cache results in your app to stay within limits. Rate limits can be configured in `.lyrica.config` per fetcher.

**Q: Can I deploy to production?**
A: Yes. Use Gunicorn (`gunicorn -c gunicorn.config.py run:app`) and optionally an Nginx reverse proxy. For high traffic, use the prehosted Hugging Face instance.

**Q: How do I get timestamped lyrics?**
A: Add `&timestamps=true`. Sources 2–7 all support timestamps. Source 1 (Genius) is plain-text only.

**Q: Why is a song not found?**
A: Try exact spelling, check internet, or use `fast=true` to run more sources in parallel.

**Q: Can I choose which sources are queried?**
A: Yes — use `&pass=true&sequence=1,3,4` with a comma-separated list of source IDs.

**Q: What happened to Lyrics.ovh, ChartLyrics, and LyricsFreek?**
A: These APIs are dead as of June 2026 and have been removed from the active source list.

**Q: Can I run the API without a Genius token?**
A: Yes. Genius (source 1) simply won't load, but all other 6 sources still work.

---

**Last Updated**: July 19, 2026 | **Version**: 1.3.0