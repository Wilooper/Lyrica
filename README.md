# Lyrica - Open Source Lyrics API

![Made in India](https://img.shields.io/badge/Made%20in-India-blue.svg) ![Python](https://img.shields.io/badge/Python-3.12%2B-brightgreen.svg) ![License](https://img.shields.io/badge/License-MIT-yellow.svg) ![Flask](https://img.shields.io/badge/Flask-3.0.0-blue.svg) ![Status](https://img.shields.io/badge/Status-Active-success.svg)

A Flask-based lyrics API for plain and timestamped lyrics, metadata, sentiment analysis, trending charts, and multi-source fallback. The current app version is 1.4.0.

## Security Notes
- Public endpoints do not require authentication.
- Admin and management endpoints require `ADMIN_KEY`.
- Optional API tokens are only used for third-party sources.
- Cookie-based YouTube auth is not required by default.

## Before You Start
- This is the Flask version. If you want the FastAPI version, visit:
  https://github.com/Wilooper/LyricaV2.git

## ✨ Key Features

- **Multi-Source Lyrics Retrieval** — Aggregates from 7 active sources with intelligent fallback and validation
- **Timestamped Lyrics (LRC)** — Line-level synchronized lyrics with millisecond precision from multiple sources
- **Word-Level Sync** — Per-word timestamps via Lrcmux/Musixmatch (`&word=true`) — ideal for karaoke and lyric-highlighting apps
- **Mood & Sentiment Analysis** — Sentiment detection and word frequency analysis
- **Rich Metadata** — Song cover art, duration, genre, release date, and artist info
- **Smart Caching** — TTL-based caching (24-hour default) to reduce external API calls
- **Rate Limiting** — 15 requests/minute per IP
- **Fast Mode** — Parallel fetching for sub-second response times
- **Proxy Rotation** — Thread-safe, round-robin rotating proxy pool with failure cooldown and auto-masking credentials; seedable via `PROXY_URL` env var
- **Lyrics Translation & Transliteration** — Translate and/or romanize lyrics on-the-fly to a preferred language/script using Groq LLM
- **User Configuration** — INI-based configuration (`.lyrica.config`) supporting hot-reloads and environment overrides
- **Trending Charts** — Real-time trending songs by country via Apple Music
- **Analytics & Auto-complete** — Search suggestions via MusicBrainz and top query metrics
- **Admin Tools** — Cache, config, and proxy pool management endpoints
- **Comprehensive Logging** — Debug and monitor with detailed request/response logs
- **Made in India** 🇮🇳 — Optimized for Indian music platforms (JioSaavn integration)

## What's New in v1.4.0
- **Word-Level Sync** (`&word=true`) — Per-word timestamps from Musixmatch via Lrcmux, perfect for karaoke highlighting
- **Lrcmux Source (ID 7)** — Musixmatch lyrics aggregated via [api.lrcmux.dev](https://api.lrcmux.dev) without a token
- **Global Proxy via ENV** — `PROXY_URL` env var seeds the shared proxy pool used by all fetchers at startup
- **YT Auth via ENV** — `YT_COOKIES_PATH` and `YT_HEADERS_PATH` allow hosted deployments to set auth file locations securely
- **Smarter Default Order** — Fetcher fallback now starts with LRCLIB → Lrcmux (most reliable synced sources first)

## 🎵 Supported Sources

| ID | Source | Lyrics Type | Notes |
|----|--------|-------------|-------|
| 1 | Genius | Plain | Requires `GENIUS_TOKEN` |
| 2 | LRCLIB | Timestamped + Plain | Free, very reliable — **tried first** |
| 3 | YouTube Music | Timestamped + Plain | 3-layer fallback (ytmusicapi → transcript-api → yt-dlp) |
| 4 | NetEase | Timestamped (LRC) | Via syncedlyrics, large catalog |
| 5 | Megalobiz | Timestamped (LRC) | Via syncedlyrics, user-contributed |
| 6 | Musixmatch | Timestamped (LRC) | Via syncedlyrics, optional `MUSIXMATCH_TOKEN` |
| 7 | Lrcmux | Timestamped + Word-Level | Musixmatch via api.lrcmux.dev — no token needed |

**Default fallback order**: 2 → 7 → 1 → 3 → 4 → 5 → 6

## 📦 Installation

### Prerequisites
- Python 3.12 or higher
- pip (Python package manager)
- Git

### Quick Start (Local Development)

```bash
# 1. Clone the repository
git clone https://github.com/Wilooper/Lyrica.git
cd Lyrica

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env file
cp .env.example .env
# Edit .env and fill in your GENIUS_TOKEN (optional)

# 5. Run the server
python run.py
```

Access the API at: `http://127.0.0.1:9999`
- Web GUI: `http://127.0.0.1:9999/app`
- API Info: `http://127.0.0.1:9999/`

### Docker Setup (Optional)

```bash
# Build image
docker build -t lyrica .

# Run container
docker run -p 9999:9999 \
  -e GENIUS_TOKEN=your_token \
  -e ADMIN_KEY=your_key \
  lyrica
```

## ⚙️ Configuration

Lyrica uses a two-tier configuration system: environment variables for system deployment (secrets, directories), and an optional `.lyrica.config` INI file for user/application level settings.

### 1. Environment Variables (`.env`)

Create a `.env` file in the project root (copy from `.env.example`):

```env
# Secure key to protect admin/management endpoints
ADMIN_KEY=your_secure_admin_key_here

# Genius API client token (Optional, source 1)
GENIUS_TOKEN=your_token

# Musixmatch client token (Optional, source 6)
MUSIXMATCH_TOKEN=your_token

# Global proxy — routes ALL fetchers through this proxy
# Supports comma-separated list for rotation
# PROXY_URL=http://user:pass@host:port

# YouTube-specific proxy (separate from global proxy)
# YT_PROXY_URL=http://user:pass@host:port

# YouTube auth file paths (for hosted/containerised deployments)
# YT_COOKIES_PATH=/absolute/path/to/cookies.txt
# YT_HEADERS_PATH=/absolute/path/to/headers_auth.json

# Rate limiting storage backend (Recommended: redis://... in production)
RATE_LIMIT_STORAGE_URI=memory://

# Caching and log levels
LOG_LEVEL=INFO
CACHE_TTL=86400
CACHE_DIR=cache_data
```

### 2. User Configuration (`.lyrica.config`)

For fine-grained control over fetchers, proxy pools, and rate limits, copy `.lyrica.config.example` to `.lyrica.config` in your project root or home directory.

Features:
- **Default settings**: Override default request params like `fast`, `timestamps`, `mood`, `metadata`, `word`, or the fetcher `sequence`.
- **Proxy rotation**: Paste list of socks5/http proxies under `[proxies]` for round-robin rotation.
- **Rate limits**: Configure requests-per-minute (RPM) limits for each fetcher to avoid IP bans.
- **Hot Reloading**: Config can watch for changes or be reloaded dynamically via `/config/reload`.

See [.lyrica.config.example](.lyrica.config.example) for detailed fields.

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ADMIN_KEY` | No | — | Secure key to access admin and management endpoints |
| `GENIUS_TOKEN` | No | — | Genius API token for Genius fetcher |
| `MUSIXMATCH_TOKEN` | No | — | Musixmatch API token for Musixmatch fetcher |
| `PROXY_URL` | No | — | Global proxy URL for all fetchers (comma-separated list supported) |
| `YT_PROXY_URL` | No | — | YouTube-only proxy URL |
| `YT_COOKIES_PATH` | No | — | Absolute path to cookies.txt (used by yt-dlp Layer 3) |
| `YT_HEADERS_PATH` | No | — | Absolute path to headers_auth.json (used by ytmusicapi) |
| `RATE_LIMIT_STORAGE_URI` | No | `memory://` | Storage backend for rate limiting |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `CACHE_TTL` | No | `86400` | Cache TTL in seconds |
| `CACHE_DIR` | No | `cache_data` | Directory for cache files |
| `GROQ_API_KEY` | No | — | Groq API key(s) for translation/romanization (comma-separated) |
| `GROQ_MODEL` | No | `llama-3.3-70b-versatile` | Groq model to use |

\* Lyrica still works without any tokens — those sources are simply skipped.


## 🚀 Deployment

### Render.com
1. Push repository to GitHub
2. Create new Web Service on Render
3. Set build command: `pip install -r requirements.txt`
4. Set start command: `gunicorn -w 4 -b 0.0.0.0:9999 run:app`
5. Add environment variables in dashboard
6. Deploy

### Self-Hosted (Gunicorn + Nginx)
```bash
# Run with 4 workers
gunicorn -w 4 -b 127.0.0.1:9999 --timeout 120 run:app

# Configure Nginx as reverse proxy (see deployment guides)
```

## NOTE
- If you don't want to self-host, you can use the prehosted server. All endpoints are the same as on localhost.
- **Link 1**: https://test-0k.onrender.com/
- **Link 2 (Recommended for production)**: https://wilooper-lyrica.hf.space/
  - The Hugging Face version is designed to handle thousands of simultaneous users with ~95% uptime.
  
## 📚 Quick API Examples

### Basic Lyrics
```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Coldplay&song=Yellow"
```

### Line-Level Timestamps
```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Coldplay&song=Yellow&timestamps=true"
```

### Word-Level Sync (for karaoke / lyric highlighting)
```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Coldplay&song=Yellow&timestamps=true&word=true"
```

### With Mood Analysis
```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho&mood=true"
```

### With Metadata
```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho&metadata=true"
```

### Fast Mode (All Features)
```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho&fast=true&timestamps=true&mood=true&metadata=true"
```

### Trending Songs (India)
```bash
curl "http://127.0.0.1:9999/trending/?country=IN&limit=10"
```

### Song Suggestions / Autocomplete
```bash
curl "http://127.0.0.1:9999/suggestion?q=Tum%20Hi%20Ho&limit=5"
```

### Lyrics Translation & Transliteration
```bash
# Get translated and romanized synced lyrics
curl "http://127.0.0.1:9999/lyrics/?artist=Karan%20Aujla&song=Boyfriend&timestamps=true&translate=true&romanize=true&language=en"

# Get translation only on plain/unsynced lyrics
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho&translate=true&language=spanish"
```

## 🛠️ Troubleshooting

### No Lyrics Found
- Verify artist and song names are correct
- Check internet connection
- Try a popular song first to verify the server is working
- Use `fast=true` to run sources in parallel for better coverage

### Genius API Errors
- Regenerate token at [genius.com/api-clients](https://genius.com/api-clients)
- Verify token in `.env`
- The API works without Genius — other sources will be tried

### YouTube Music Blocks & Rate Limits
- YouTube Music fetcher runs a robust 3-layer fallback system (ytmusicapi → transcript-api → yt-dlp subtitles) which does not require cookies out of the box!
- If your IP gets rate-limited by YouTube, set `YT_PROXY_URL` in `.env` to route through a proxy.
- For containerised deployments, use `YT_COOKIES_PATH` and `YT_HEADERS_PATH` env vars instead of placing files in the project root.

### Rate Limit Issues (Flask-Limiter)
- The local server limits clients to 15 requests per minute per IP.
- Cache results or configure a Redis backend using `RATE_LIMIT_STORAGE_URI` for higher limits.

### Port Already in Use
Edit `run.py`:
```python
if __name__ == '__main__':
    app.run(port=8080, debug=True)  # Change 9999 to 8080
```

## 📖 Documentation

- **Full API Reference**: See [USER_GUIDE.md](USER_GUIDE.md)
- **Word-Level Sync Guide**: See [WORD_SYNC_GUIDE.md](WORD_SYNC_GUIDE.md)
- **Lyrics Translation Guide**: See [TRANSLATION_GUIDE.md](TRANSLATION_GUIDE.md)
- **Setup Details**: See [SETUP_GUIDE.md](SETUP_GUIDE.md)
- **Issues**: Open GitHub issues for bugs or feature requests

## 🤝 Contributing

Contributions are welcome!

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open Pull Request

Please ensure:
- Code follows PEP 8 style guide
- Documentation is updated for any new or changed features
- Commit messages are descriptive

You can also suggest changes by opening an issue — all suggestions are welcome!

## 📝 License

MIT License © 2025 Lyrica Contributors

See [LICENSE](LICENSE) file for details.
## Contributors

<!-- readme: contributors -start -->
<table>
	<tbody>
		<tr>
            <td align="center">
                <a href="https://github.com/Wilooper">
                    <img src="https://avatars.githubusercontent.com/u/198341775?v=4" width="100;" alt="Wilooper"/>
                    <br />
                    <sub><b>Shaurya singh</b></sub>
                </a>
            </td>
            <td align="center">
                <a href="https://github.com/rombat">
                    <img src="https://avatars.githubusercontent.com/u/9024503?v=4" width="100;" alt="rombat"/>
                    <br />
                    <sub><b>Romain Batigne</b></sub>
                </a>
            </td>
            <td align="center">
                <a href="https://github.com/shelbeely">
                    <img src="https://avatars.githubusercontent.com/u/2256469?v=4" width="100;" alt="shelbeely"/>
                    <br />
                    <sub><b>Shelbee Johnson </b></sub>
                </a>
            </td>
		</tr>
	<tbody>
</table>
<!-- readme: contributors -end -->

## 🙏 Special Thanks

- **sigma67** — [ytmusicapi](https://github.com/sigma67/ytmusicapi)
- **tranxuanthang & LrcLib Team** — LRC lyrics support
- **lrcmux team** — Musixmatch aggregation without a token
- **JioSaavn** — Music metadata and streaming
- **syncedlyrics** — NetEase, Megalobiz, Musixmatch integration
- **MusicBrainz** — Song suggestion/autocomplete data

## 📞 Support

- **Documentation**: [USER_GUIDE.md](USER_GUIDE.md)
- **Issues**: [GitHub Issues](https://github.com/Wilooper/Lyrica/issues)
- **Discussions**: [GitHub Discussions](https://github.com/Wilooper/Lyrica/discussions)
- **Email**: wiloooper@proton.me

---
**Current Version**: 1.4.0

**Reference**: GitHub release metadata and the current API health response

Made with ❤️ in India 🇮🇳
