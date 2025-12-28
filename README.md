# Lyrica API Documentation

![Made in India](https://img.shields.io/badge/Made%20in-India-blue.svg) ![Python](https://img.shields.io/badge/Python-3.12%2B-brightgreen.svg) ![License](https://img.shields.io/badge/License-MIT-yellow.svg) ![Flask](https://img.shields.io/badge/Flask-3.0.0-blue.svg)

## Overview

**Lyrica** is an open-source RESTful API for retrieving song lyrics from multiple sources, developed with a focus on accessibility and reliability in India 🇮🇳. It prioritizes high-quality sources like YouTube Music for timestamped lyrics and falls back to LrcLib, Genius, Lyrics.ovh, ChartLyrics, LyricsFreak, and Simp Music for comprehensive coverage. The API is built on Flask, supports asynchronous operations, includes caching for performance, rate limiting for stability, CORS for web integration, and detailed logging for debugging.

# IMPORTANAT NOTE to users:-


- **I have made a lyrics translation and transliteration engine if you are inatrested then you can check it out on:-
-https://automatic-engine-nc2j.onrender.com**
-It might be slow now because it uses ai to translate and transliterate we will soon implement the database to make it fast asap
ALSO if you like the project then star it
**THANKS!**
### Key Features
- **Multi-Source Lyrics Retrieval**: Aggregates from 7 sources with prioritized sequencing.
- **Timestamped Lyrics**: Supports synchronized (LRC-style) lyrics from YouTube Music and LrcLib.
- **Caching**: TTL-based (default: 5 minutes) to minimize external API calls.
- **Rate Limiting**: 15 requests per minute per IP (customizable via Redis).
- **CORS-Enabled**: Ideal for frontend applications.
- **Admin Tools**: Secure endpoints for cache management.
- **GUI Tester**: Built-in web interface for interactive testing.
- **Made in India**: Optimized for Bollywood and regional music queries.

### Base URL
- **Local Development**: `http://127.0.0.1:9999`
- **Production Demo**: `https://test-0k.onrender.com`

### Version
- Current: `1.2.0`

## Authentication and Configuration

Lyrica does not require user authentication but relies on environment variables for external services:

- **GENIUS_TOKEN**: Required for Genius API fallback (obtain from [Genius API Clients](https://genius.com/api-clients)).
- **YOUTUBE_COOKIE**: Optional for enhanced YouTube Music access.
- **ADMIN_KEY**: Required for admin cache endpoints.
- **RATE_LIMIT_STORAGE_URI**: Defaults to `memory://`; use `redis://` for production.

Set these in a `.env` file or deployment platform dashboard.

## Quick Start

1. **Clone and Install**:
   ```
   git clone https://github.com/Wilooper/Lyrica.git
   cd Lyrica
   pip install -r requirements.txt
   ```

2. **Configure Environment**:
   Create `.env`:
   ```
   GENIUS_TOKEN=your_genius_token
   ADMIN_KEY=your_secure_key
   ```

3. **Run Locally**:
   ```
   python run.py
   ```
   Access at `http://127.0.0.1:9999`.

4. **Test with GUI**:
   Visit `http://127.0.0.1:9999/app` for an interactive interface.

5. **Deploy** (e.g., Render):
   - Push to GitHub.
   - Connect to Render, set env vars, and deploy as a Web Service.

## API Endpoints

All endpoints return JSON responses. Use URL-encoding for parameters (e.g., spaces as `%20`).

### 1. API Metadata
- **URL**: `GET /`
- **Description**: Retrieves API status, version, and endpoint summary.
- **Parameters**: None.
- **Example Request**:
  ```
  curl http://127.0.0.1:9999/
  ```
- **Response** (200 OK):
  ```json
  {
    "api": "Lyrica",
    "version": "1.2.0",
    "status": "active",
    "endpoints": {
      "lyrics": "/lyrics/?artist=ARTIST&song=SONG&timestamps=true&pass=false&sequence=1,2,3",
      "cache": "/cache/stats",
      "gui": "/app"
    },
    "timestamp": "2025-12-25 12:20:00"
  }
  ```

### 2. Fetch Lyrics
- **URL**: `GET /lyrics/`
- **Description**: Searches for lyrics by artist and song, attempting sources in sequence. Supports custom source ordering and timestamped results.
- **Parameters**:
  | Parameter   | Type    | Required | Description                                                                 | Default |
  |-------------|---------|----------|-----------------------------------------------------------------------------|---------|
  | `artist`    | string  | Yes      | Artist name (e.g., "Arijit Singh").                                         | -       |
  | `song`      | string  | Yes      | Song title (e.g., "Tum Hi Ho").                                             | -       |
  | `timestamps`| boolean | No       | Enable timestamped lyrics (only from YouTube Music/LrcLib).                 | false   |
  | `pass`      | boolean | No       | Enable custom source sequence.                                              | false   |
  | `sequence`  | string  | No       | Comma-separated source IDs (e.g., "1,3,5"); requires `pass=true`.           | -       |

  **Source Sequence**:
  - 1: YouTube Music
  - 2: LrcLib
  - 3: Genius
  - 4: Lyrics.ovh
  - 5: ChartLyrics
  - 6: LyricsFreak
  - 7: Simp Music

- **Example Requests**:
  - Basic (plain lyrics):
    ```
    curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho"
    ```
  - With timestamps:
    ```
    curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho&timestamps=true"
    ```
  - Custom sequence (skip LrcLib):
    ```
    curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho&pass=true&sequence=1,3,4"
    ```

- **Success Response** (200 OK, plain lyrics):
  ```json
  {
    "status": "success",
    "data": {
      "source": "genius",
      "artist": "Arijit Singh",
      "title": "Tum Hi Ho",
      "lyrics": "Hum tere bin ab reh nahi sakte\nTere bina kya wajood mera...",
      "timestamp": "2025-12-25 12:20:00"
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

- **Success Response** (200 OK, timestamped):
  ```json
  {
    "status": "success",
    "data": {
      "source": "youtube_music",
      "artist": "Arijit Singh",
      "title": "Tum Hi Ho",
      "lyrics": "Hum tere bin ab reh nahi sakte\nTere bina kya wajood mera...",
      "timed_lyrics": [
        {
          "text": "Hum tere bin ab reh nahi sakte",
          "start_time": 0,
          "end_time": 10000,
          "id": 1
        }
      ],
      "hasTimestamps": true,
      "timestamp": "2025-12-25 12:20:00"
    },
    "attempts": []
  }
  ```

- **Error Response** (400 Bad Request, missing params):
  ```json
  {
    "status": "error",
    "error": {
      "message": "Artist and song name are required",
      "timestamp": "2025-12-25 12:20:00"
    }
  }
  ```

- **Error Response** (404 Not Found, no lyrics):
  ```json
  {
    "status": "error",
    "error": {
      "message": "No lyrics found for 'Tum Hi Ho' by 'Arijit Singh'",
      "attempts": [
        {"api": "youtube_music", "status": "no_results"},
        {"api": "lrclib", "status": "no_results"},
        {"api": "genius", "status": "no_results"}
      ]
    },
    "timestamp": "2025-12-25 12:20:00"
  }
  ```

- **JavaScript Example** (Frontend Integration):
  ```javascript
  fetch('http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho&timestamps=true')
    .then(response => response.json())
    .then(data => {
      if (data.status === 'success') {
        console.log('Lyrics:', data.data.lyrics);
        if (data.data.hasTimestamps) {
          console.log('Timed Lines:', data.data.timed_lyrics);
        }
      } else {
        console.error('Error:', data.error.message);
      }
    })
    .catch(error => console.error('Fetch error:', error));
  ```

### 3. Cache Management (Admin Only)
- **Clear Cache**:
  - **URL**: `POST /cache/clear` or `GET /admin/cache/clear?key={ADMIN_KEY}`
  - **Description**: Clears all cached lyrics entries.
  - **Example**:
    ```
    curl -X POST http://127.0.0.1:9999/cache/clear
    ```
  - **Response** (200 OK):
    ```json
    {
      "status": "success",
      "details": {"cleared": 42, "timestamp": "2025-12-25 12:20:00"}
    }
    ```
  - **Error** (403 Forbidden, invalid key):
    ```json
    {"error": "unauthorized"}
    ```

- **Cache Stats**:
  - **URL**: `GET /cache/stats` or `GET /admin/cache/stats?key={ADMIN_KEY}`
  - **Description**: Returns cache hit/miss ratios and entry counts.
  - **Example**:
    ```
    curl "http://127.0.0.1:9999/admin/cache/stats?key=your_admin_key"
    ```
  - **Response** (200 OK):
    ```json
    {
      "status": "success",
      "hits": 150,
      "misses": 50,
      "total_entries": 200,
      "timestamp": "2025-12-25 12:20:00"
    }
    ```

### 4. Interactive GUI
- **URL**: `GET /app`
- **Description**: A simple web-based tester for the `/lyrics/` endpoint. Enter artist/song details and view results in real-time.
- **Example**: Navigate to `http://127.0.0.1:9999/app` in a browser.

## Rate Limiting and Errors

- **Rate Limit**: 15 requests/minute per IP. Exceeding triggers 429 Too Many Requests:
  ```json
  {
    "status": "error",
    "error": {
      "message": "Rate limit exceeded. Please wait 35 seconds before retrying."
    }
  }
  ```
  Header: `Retry-After: 35`

- **Common Errors**:
  - 400: Invalid/missing parameters.
  - 403: Admin access denied.
  - 429: Rate limit exceeded.
  - 500: Internal server error (check logs).

## Usage Best Practices

- **Query Tips**: Use exact names (e.g., "Arijit Singh" not "Arijit"). Popular songs succeed more often.
- **Timestamps**: Request only when needed; falls back gracefully if unavailable.
- **Custom Sequences**: Use for optimization (e.g., skip slow sources: `&pass=true&sequence=3,4,5`).
- **Caching**: Responses are cached for 5 minutes; use admin tools to invalidate.
- **Monitoring**: Enable logging (`LOG_LEVEL=DEBUG` in `.env`) for troubleshooting.
- **Production Scaling**: Integrate Redis for distributed caching/rate limiting.

## Deployment Guide

- **Local**: `python run.py`
- **Production (Gunicorn)**:
  ```
  gunicorn -w 4 -b 0.0.0.0:9999 run:app
  ```
- **Platforms**: Render, Heroku, Vercel. Set env vars securely.
- **Docker** (Optional): See `Dockerfile` in repo for containerization.

## Troubleshooting

- **No Lyrics**: Verify env vars; test popular songs; check server logs.
- **Auth Failures**: Re-run `ytmusicapi setup` for YouTube; regenerate Genius token.
- **Rate Limits**: Switch to Redis backend.
- **Port Conflicts**: Edit `run.py` to change `app.run(port=8080)`.
- **Dependencies**: Run `pip install flask[async]` if async issues arise.

## Contributing

Contributions are encouraged! Fork the repo, create a feature branch, add tests, and submit a PR. Follow PEP 8 and update docs as needed. Report issues via GitHub.

## Special Thanks

- **sigma67**: For `ytmusicapi`.
- **tranxuanthang & LrcLib Team**: For LRC support.
- **maxrave-dev**: For Simp Music integration.

## License

MIT License. See [LICENSE](LICENSE) for details.

---

For questions, open a GitHub issue. Happy coding with Lyrica! 🇮🇳
