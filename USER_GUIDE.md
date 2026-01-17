# Lyrica - Complete User Guide & API Reference

## Table of Contents

1. [Getting Started](#getting-started)
2. [API Endpoints](#api-endpoints)
3. [Core Features](#core-features)
4. [Response Formats](#response-formats)
5. [Error Handling](#error-handling)
6. [Best Practices](#best-practices)
7. [Code Examples](#code-examples)
8. [OpenAPI Specification](#openapi-specification)

---

## Getting Started

### Base URLs

- **Local Development**: `http://127.0.0.1:9999`
- **Production Demo**: `https://test-0k.onrender.com`
- **API Documentation**: `/` (root endpoint)
- **Swagger UI**: `/swagger` or `/swagger-ui`
- **Web GUI**: `/app`

### Authentication

Lyrica does not require authentication for public endpoints. Admin endpoints require:

```bash
# Method 1: Query parameter
GET /cache/clear?key=your_admin_key

# Method 2: Request header
Authorization: Bearer your_admin_key
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
| `artist` | string | Yes | - | Artist name (e.g., "Arijit Singh") |
| `song` | string | Yes | - | Song title (e.g., "Tum Hi Ho") |
| `timestamps` | boolean | No | false | Include synchronized LRC timestamps |
| `mood` | boolean | No | false | Include sentiment & word analysis |
| `metadata` | boolean | No | false | Include song metadata (cover, duration, genre) |
| `fast` | boolean | No | false | Use parallel fetching for speed |
| `pass` | boolean | No | false | Enable custom fetcher sequence |
| `sequence` | string | No | - | Custom fetcher IDs (e.g., "1,3,5") |

#### Source Sequence IDs

- **1** → Genius (comprehensive lyrics, good quality)
- **2** → LRCLIB (timestamped lyrics)
- **3** → SimpMusic (fast, reliable)
- **4** → YouTube Music (timestamped, premium quality)
- **5** → Lyrics.ovh (fast fallback)
- **6** → ChartLyrics (secondary fallback)

**Default Sequences:**
- Plain lyrics: `[1, 2, 3, 4, 5, 6]`
- With timestamps: `[2, 3, 4]` (only sources with timestamps)

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

**Custom Source Sequence (Skip LRCLIB)**
```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho&pass=true&sequence=1,3,4,5"
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
    "timestamp": "2025-01-15T12:20:00+00:00"
  },
  "attempts": [
    {
      "api": "youtube_music",
      "status": "no_results",
      "message": "No lyrics available"
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
    "plain_lyrics": "Hum tere bin ab reh nahi sakte\nTere bina kya wajood mera...",
    "lyrics": "Hum tere bin ab reh nahi sakte\nTere bina kya wajood mera...",
    "timed_lyrics": [
      {
        "text": "Hum tere bin ab reh nahi sakte",
        "start_time": 0,
        "end_time": 10000,
        "id": 1
      },
      {
        "text": "Tere bina kya wajood mera",
        "start_time": 10000,
        "end_time": 20000,
        "id": 2
      }
    ],
    "hasTimestamps": true,
    "timestamp": "2025-01-15T12:20:00+00:00"
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
    "lyrics": "...",
    "timestamp": "2025-01-15T12:20:00+00:00"
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

**Missing Parameters (400 Bad Request)**
```json
{
  "status": "error",
  "error": {
    "message": "Artist and song name are required",
    "timestamp": "2025-01-15T12:20:00+00:00"
  }
}
```

**No Lyrics Found (404 Not Found)**
```json
{
  "status": "error",
  "error": {
    "message": "No lyrics found for 'XYZ' by 'Unknown Artist'",
    "attempts": [
      {"api": "genius", "status": "no_results"},
      {"api": "lrclib", "status": "no_results"},
      {"api": "youtube_music", "status": "no_results"}
    ]
  },
  "timestamp": "2025-01-15T12:20:00+00:00"
}
```

**Rate Limit Exceeded (429 Too Many Requests)**
```json
{
  "status": "error",
  "error": {
    "message": "Rate limit exceeded. Please wait 45 seconds before retrying.",
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

### 3. JioSaavn Search Endpoint

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

### 4. JioSaavn Play Endpoint

**Get playable stream URL from JioSaavn**

```
GET /api/jiosaavn/play
```

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `songLink` | string | Yes | Song link from JioSaavn search |

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

### 5. Cache Statistics Endpoint

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
  "timestamp": "2025-01-15T12:20:00+00:00"
}
```

---

### 6. Cache Clear Endpoint (Admin)

**Clear all cached lyrics**

```
POST /cache/clear
GET /admin/cache/clear?key=your_admin_key
```

#### Example Requests

```bash
# Using POST
curl -X POST http://127.0.0.1:9999/cache/clear

# Using GET with admin key
curl "http://127.0.0.1:9999/admin/cache/clear?key=your_admin_key"
```

#### Response

```json
{
  "status": "success",
  "details": {
    "cleared": 150,
    "timestamp": "2025-01-15T12:20:00+00:00"
  }
}
```

#### Error (403 Forbidden)

```json
{
  "status": "error",
  "error": {
    "message": "Unauthorized - Invalid admin key"
  }
}
```

---

### 7. Web GUI Endpoint

**Interactive web interface for testing**

```
GET /app
```

Navigate to `http://127.0.0.1:9999/app` in your browser.

---

### 8. API Metadata Endpoint

**Get API version, status, and endpoint documentation**

```
GET /
```

#### Response

```json
{
  "api": "Lyrica",
  "version": "1.2.0",
  "status": "active",
  "description": "A comprehensive lyrics API with mood analysis and metadata extraction",
  "timestamp": "2025-01-15T12:20:00+00:00",
  "endpoints": {
    "lyrics": {
      "url": "/lyrics/",
      "method": "GET",
      "description": "Fetch lyrics for a song"
    },
    "metadata": {
      "url": "/metadata/",
      "method": "GET",
      "description": "Get song metadata without lyrics"
    },
    "cache_stats": {
      "url": "/cache/stats",
      "method": "GET",
      "description": "Get cache statistics"
    }
  },
  "fetchers": {
    "1": "Genius",
    "2": "LRCLIB",
    "3": "SimpMusic",
    "4": "YouTube Music",
    "5": "Lyrics.ovh",
    "6": "ChartLyrics"
  }
}
```

---

## Core Features

### Feature 1: Timestamped Lyrics (LRC Format)

Get lyrics synchronized with millisecond precision.

**Use Case:** Display lyrics as song plays in real-time.

```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho&timestamps=true"
```

**Response Example:**
```json
{
  "data": {
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
    "hasTimestamps": true
  }
}
```

### Feature 2: Mood & Sentiment Analysis

Understand the emotional tone of lyrics.

**Use Case:** Show mood tags on music player, create mood-based playlists.

```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho&mood=true"
```

**Analysis Includes:**
- **Polarity**: -1 (negative) to +1 (positive)
- **Subjectivity**: 0 (objective) to 1 (subjective)
- **Emotion**: sad, happy, energetic, calm, etc.
- **Top Words**: Most frequently used meaningful words

**Response Example:**
```json
{
  "mood_analysis": {
    "sentiment": {
      "polarity": -0.45,
      "subjectivity": 0.75,
      "emotion": "sad, romantic",
      "confidence": 0.87
    },
    "top_words": [
      {"word": "love", "frequency": 12},
      {"word": "heart", "frequency": 8},
      {"word": "night", "frequency": 7},
      {"word": "dream", "frequency": 6},
      {"word": "forever", "frequency": 5}
    ]
  }
}
```

### Feature 3: Rich Metadata

Get comprehensive song information.

**Use Case:** Display song details in app UI, show album art, filter by genre.

```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho&metadata=true"
```

**Metadata Includes:**
- Album artwork (high-resolution)
- Duration
- Genre
- Release date
- Album name
- Producer/Writer credits
- Explicit content flag

### Feature 4: Fast Mode (Parallel Fetching)

Get results in sub-second time by checking multiple sources simultaneously.

**Use Case:** Fast search features, real-time autocomplete.

```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho&fast=true"
```

**Performance:**
- Default: ~500-2000ms
- Fast Mode: ~300-800ms
- With caching: <50ms

### Feature 5: Custom Source Sequencing

Control which sources to query and in what order.

**Use Case:** Optimize for your needs (speed vs. quality).

```bash
# Skip slow sources, use fast ones only
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho&pass=true&sequence=3,5,6"

# Prioritize timestamped sources
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho&timestamps=true&pass=true&sequence=4,2"
```

### Feature 6: Intelligent Caching

Reduce API calls with smart TTL-based caching.

**Benefits:**
- 5-minute default cache
- Redis support for distributed systems
- Admin cache management
- Cache statistics

```bash
# View cache stats
curl "http://127.0.0.1:9999/cache/stats"

# Clear cache (admin)
curl -X POST http://127.0.0.1:9999/cache/clear?key=your_admin_key
```

---

## Response Formats

### Standard Response Structure

All responses follow this format:

```json
{
  "status": "success" | "error",
  "data": {
    // Response-specific data
  },
  "error": {
    // Only present if status is "error"
    "message": "Human-readable error message",
    "details": "Optional detailed error info"
  },
  "timestamp": "ISO 8601 timestamp",
  "attempts": [
    // Only in lyrics endpoint - shows fallback attempts
    {
      "api": "source_name",
      "status": "success" | "no_results" | "error",
      "message": "Optional message"
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
| 400 | Bad Request | Missing required parameters |
| 404 | Not Found | No lyrics available for song |
| 429 | Rate Limited | Too many requests in short time |
| 500 | Server Error | Internal processing error |

### Common Errors and Solutions

**Error: "Artist and song name are required"**
```
Cause: Missing artist or song parameter
Solution: Include both ?artist=X&song=Y in request
```

**Error: "No lyrics found"**
```
Cause: Song not available in any source
Solution: Try exact spelling, popular songs first, check internet
```

**Error: "Rate limit exceeded"**
```
Cause: >15 requests per minute from your IP
Solution: Wait indicated time, use caching, consider Redis for production
```

**Error: "Failed to fetch lyrics"**
```
Cause: Network or API error
Solution: Check internet, verify API keys, check server logs
```

---

## Best Practices

### 1. Parameter Encoding

Always URL-encode special characters:

```bash
# Good
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho"

# Bad (spaces not encoded)
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit Singh&song=Tum Hi Ho"
```

### 2. Caching Strategy

- Request basic lyrics first, cache result
- Use fast mode for time-critical requests
- Store results in your app's cache for 1-2 minutes
- Clear cache after song updates

### 3. Error Handling

```javascript
// Always check status
if (response.data.status === 'error') {
  console.error(response.data.error.message);
  // Handle gracefully
}
```

### 4. Request Optimization

```bash
# Instead of 3 requests
curl "...&lyrics..." 
curl "...&timestamps..."
curl "...&mood..."

# Use 1 request with all options
curl "...&timestamps=true&mood=true&metadata=true&fast=true"
```

### 5. Rate Limiting

- Implement client-side throttling
- Cache results aggressively
- Use custom sequences to reduce fallback attempts
- Consider Redis for production environments

### 6. Custom Sequences

```bash
# Fast mode (skip slow sources)
sequence=3,5,6  # SimpMusic, Lyrics.ovh, ChartLyrics

# Quality mode (prefer detailed sources)
sequence=1,4,2  # Genius, YouTube Music, LRCLIB

# Timestamped mode (only synced sources)
sequence=2,4    # LRCLIB, YouTube Music
```

---

## Code Examples

### JavaScript/Fetch API

```javascript
async function getLyrics(artist, song, options = {}) {
  const params = new URLSearchParams({
    artist,
    song,
    timestamps: options.timestamps || false,
    mood: options.mood || false,
    metadata: options.metadata || false,
    fast: options.fast || false
  });

  try {
    const response = await fetch(
      `http://127.0.0.1:9999/lyrics/?${params}`
    );
    const data = await response.json();

    if (data.status === 'success') {
      return {
        lyrics: data.data.lyrics,
        source: data.data.source,
        mood: data.mood_analysis || null,
        metadata: data.data.metadata || null,
        timedLyrics: data.data.timed_lyrics || null
      };
    } else {
      throw new Error(data.error.message);
    }
  } catch (error) {
    console.error('Failed to fetch lyrics:', error);
    throw error;
  }
}

// Usage
getLyrics('Arijit Singh', 'Tum Hi Ho', {
  timestamps: true,
  mood: true,
  metadata: true,
  fast: true
}).then(lyrics => {
  console.log(lyrics);
}).catch(error => {
  console.error(error);
});
```

### Python/Requests

```python
import requests

def get_lyrics(artist, song, **options):
    params = {
        'artist': artist,
        'song': song,
        'timestamps': options.get('timestamps', False),
        'mood': options.get('mood', False),
        'metadata': options.get('metadata', False),
        'fast': options.get('fast', False)
    }
    
    response = requests.get('http://127.0.0.1:9999/lyrics/', params=params)
    data = response.json()
    
    if data['status'] == 'success':
        return {
            'lyrics': data['data']['lyrics'],
            'source': data['data']['source'],
            'mood': data.get('mood_analysis'),
            'metadata': data['data'].get('metadata')
        }
    else:
        raise Exception(data['error']['message'])

# Usage
try:
    lyrics = get_lyrics(
        'Arijit Singh',
        'Tum Hi Ho',
        timestamps=True,
        mood=True,
        metadata=True,
        fast=True
    )
    print(lyrics)
except Exception as e:
    print(f"Error: {e}")
```

### cURL

```bash
#!/bin/bash

ARTIST="Arijit Singh"
SONG="Tum Hi Ho"
API_URL="http://127.0.0.1:9999"

# Fetch with all features
curl "${API_URL}/lyrics/?artist=$(echo $ARTIST | tr ' ' '%20')&song=$(echo $SONG | tr ' ' '%20')&fast=true&timestamps=true&mood=true&metadata=true" | jq '.'
```

---

## OpenAPI Specification

### Swagger/OpenAPI 3.0 Definition

```yaml
openapi: 3.0.0
info:
  title: Lyrica API
  version: 1.2.0
  description: Open-source RESTful API for song lyrics retrieval with mood analysis
  contact:
    name: Lyrica Contributors
    url: https://github.com/Wilooper/Lyrica
  license:
    name: MIT
    url: https://opensource.org/licenses/MIT

servers:
  - url: http://127.0.0.1:9999
    description: Local Development
  - url: https://test-0k.onrender.com
    description: Production Demo

tags:
  - name: Lyrics
    description: Retrieve song lyrics with optional features
  - name: Metadata
    description: Song information and metadata
  - name: JioSaavn
    description: Indian music platform integration
  - name: Cache
    description: Cache management (admin only)
  - name: Utility
    description: Utility and status endpoints

paths:
  /:
    get:
      tags:
        - Utility
      summary: API Status and Documentation
      description: Get API version, status, and endpoint summary
      responses:
        '200':
          description: API information
          content:
            application/json:
              schema:
                type: object
                properties:
                  api:
                    type: string
                  version:
                    type: string
                  status:
                    type: string
                  endpoints:
                    type: object

  /lyrics/:
    get:
      tags:
        - Lyrics
      summary: Fetch Song Lyrics
      description: Retrieve lyrics from multiple sources with optional timestamps, mood analysis, and metadata
      parameters:
        - name: artist
          in: query
          required: true
          schema:
            type: string
          example: Arijit Singh
          description: Artist name
        - name: song
          in: query
          required: true
          schema:
            type: string
          example: Tum Hi Ho
          description: Song title
        - name: timestamps
          in: query
          schema:
            type: boolean
            default: false
          description: Include synchronized LRC timestamps
        - name: mood
          in: query
          schema:
            type: boolean
            default: false
          description: Include sentiment and word frequency analysis
        - name: metadata
          in: query
          schema:
            type: boolean
            default: false
          description: Include song metadata (cover, duration, genre)
        - name: fast
          in: query
          schema:
            type: boolean
            default: false
          description: Use parallel fetching for faster results
        - name: pass
          in: query
          schema:
            type: boolean
            default: false
          description: Enable custom fetcher sequence
        - name: sequence
          in: query
          schema:
            type: string
            example: "1,3,5"
          description: Custom fetcher IDs (requires pass=true)
      responses:
        '200':
          description: Lyrics retrieved successfully
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                    enum: [success]
                  data:
                    type: object
                    properties:
                      source:
                        type: string
                      artist:
                        type: string
                      title:
                        type: string
                      lyrics:
                        type: string
                      plain_lyrics:
                        type: string
                      timed_lyrics:
                        type: array
                        items:
                          type: object
                          properties:
                            text:
                              type: string
                            start_time:
                              type: integer
                            end_time:
                              type: integer
                            id:
                              type: integer
                      hasTimestamps:
                        type: boolean
                      metadata:
                        type: object
        '400':
          description: Missing required parameters
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                    enum: [error]
                  error:
                    type: object
                    properties:
                      message:
                        type: string
        '404':
          description: No lyrics found
        '429':
          description: Rate limit exceeded
          headers:
            Retry-After:
              schema:
                type: integer
              description: Seconds to wait before retrying
        '500':
          description: Internal server error

  /metadata/:
    get:
      tags:
        - Metadata
      summary: Get Song Metadata
      description: Retrieve song metadata without lyrics
      parameters:
        - name: artist
          in: query
          required: true
          schema:
            type: string
        - name: song
          in: query
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Metadata retrieved successfully
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  data:
                    type: object
                    properties:
                      cover_art:
                        type: string
                        format: uri
                      duration:
                        type: string
                      genre:
                        type: string
                      release_date:
                        type: string
                      album:
                        type: string

  /api/jiosaavn/search:
    get:
      tags:
        - JioSaavn
      summary: Search Songs on JioSaavn
      description: Search for songs on JioSaavn music platform
      parameters:
        - name: q
          in: query
          required: true
          schema:
            type: string
          example: Tum Hi Ho
          description: Search query
      responses:
        '200':
          description: Search results
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  results:
                    type: array
                    items:
                      type: object

  /api/jiosaavn/play:
    get:
      tags:
        - JioSaavn
      summary: Get JioSaavn Stream URL
      description: Get playable stream URL from JioSaavn
      parameters:
        - name: songLink
          in: query
          required: true
          schema:
            type: string
          description: Song link from JioSaavn search
      responses:
        '200':
          description: Stream URL retrieved
          content:
            application/json:
              schema:
                type: object

  /cache/stats:
    get:
      tags:
        - Cache
      summary: Get Cache Statistics
      description: Retrieve cache hit/miss ratios and entry counts
      responses:
        '200':
          description: Cache statistics
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  hits:
                    type: integer
                  misses:
                    type: integer
                  total_entries:
                    type: integer
                  hit_rate:
                    type: string

  /cache/clear:
    post:
      tags:
        - Cache
      summary: Clear Cache (Admin)
      description: Clear all cached lyrics entries (requires admin key)
      parameters:
        - name: key
          in: query
          schema:
            type: string
          description: Admin API key
      responses:
        '200':
          description: Cache cleared successfully
        '403':
          description: Unauthorized - invalid admin key

  /app:
    get:
      tags:
        - Utility
      summary: Web GUI
      description: Interactive web interface for testing the API
      responses:
        '200':
          description: HTML page served

components:
  schemas:
    LyricsResponse:
      type: object
      properties:
        status:
          type: string
        data:
          type: object
        mood_analysis:
          type: object
        timestamp:
          type: string
    
    ErrorResponse:
      type: object
      properties:
        status:
          type: string
          enum: [error]
        error:
          type: object
          properties:
            message:
              type: string
            details:
              type: string
        timestamp:
          type: string
```

---

## Installation & Configuration Reference

### Full Setup Checklist

- [ ] Python 3.12+ installed
- [ ] Clone repository: `git clone https://github.com/Wilooper/Lyrica.git`
- [ ] Create virtual environment: `python -m venv venv`
- [ ] Activate environment: `source venv/bin/activate`
- [ ] Install dependencies: `pip install -r requirements.txt`
- [ ] Create `.env` file with API keys
- [ ] Run server: `python run.py`
- [ ] Test API at `http://127.0.0.1:9999`
- [ ] Access GUI at `http://127.0.0.1:9999/app`

### Obtaining API Keys

**Genius API Token:**
1. Visit https://genius.com/api-clients
2. Create account or login
3. Create new API Client
4. Copy access token
5. Add to `.env`: `GENIUS_TOKEN=your_token`

**YouTube Music (Optional):**
```bash
pip install ytmusicapi
ytmusicapi setup
```

---

## Frequently Asked Questions

**Q: Is authentication required?**
A: No for public endpoints. Admin endpoints use an API key.

**Q: What's the rate limit?**
A: 15 requests/minute per IP. Use caching to stay within limits.

**Q: Can I deploy to production?**
A: Yes! Use Gunicorn, Nginx reverse proxy, and Redis for distributed caching.

**Q: How do I get timestamped lyrics?**
A: Add `&timestamps=true` to your request (only from LRCLIB and YouTube Music).

**Q: Why is a song not found?**
A: Try exact spelling, check internet connection, or try a more popular song first.

**Q: Can I customize which sources are queried?**
A: Yes! Use `&pass=true&sequence=1,3,5` to control source order.

---

**Last Updated**: January 15, 2026 | **Version**: 1.2.0