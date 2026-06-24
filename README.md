# Lyrica - Open Source Lyrics API

![Made in India](https://img.shields.io/badge/Made%20in-India-blue.svg) ![Python](https://img.shields.io/badge/Python-3.12%2B-brightgreen.svg) ![License](https://img.shields.io/badge/License-MIT-yellow.svg) ![Flask](https://img.shields.io/badge/Flask-3.0.0-blue.svg) ![Status](https://img.shields.io/badge/Status-Active-success.svg)

A powerful, open-source RESTful API for retrieving song lyrics with advanced features like mood analysis, timestamped lyrics, metadata extraction, trending charts, and multi-source aggregation. Built with Python and Flask, optimized for Bollywood and global music queries.

## Before You Start
- This is the Flask version. If you want the FastAPI version, visit:
  https://github.com/Wilooper/LyricaV2.git

## ✨ Key Features

- **Multi-Source Lyrics Retrieval** — Aggregates from 7 active sources with intelligent fallback and validation
- **Timestamped Lyrics (LRC)** — Synchronized lyrics with millisecond precision from multiple sources
- **Mood & Sentiment Analysis** — Sentiment detection and word frequency analysis
- **Rich Metadata** — Song cover art, duration, genre, release date, and artist info
- **Smart Caching** — TTL-based caching (1 hour default) to reduce external API calls
- **Rate Limiting** — 15 requests/minute per IP
- **Fast Mode** — Parallel fetching for sub-second response times
- **Trending Charts** — Real-time trending songs by country via Apple Music
- **Analytics** — Top user queries and trending/query intersection insights
- **Song Suggestions** — Autocomplete via MusicBrainz
- **CORS-Enabled** — Production-ready for frontend integration
- **Interactive GUI** — Built-in web interface for testing and exploration
- **Admin Tools** — Cache management and statistics endpoints
- **Comprehensive Logging** — Debug and monitor with detailed request/response logs
- **Made in India** 🇮🇳 — Optimized for Indian music platforms (JioSaavn integration)

## What's New
- Added `/trending/` endpoint — top trending content for any country via Apple Music
- Added `/analytics/top-queries/` — see your server's most queried songs
- Added `/analytics/trending-by-country/`, `/analytics/trending-vs-queries/`, `/analytics/trending-intersection/` — advanced analytics
- Added `/suggestion` — MusicBrainz-powered song autocomplete
- Refreshed sources: removed dead APIs (Lyrics.ovh, ChartLyrics, LyricsFreek), added NetEase, Megalobiz, Musixmatch

## 🎵 Supported Sources

| ID | Source | Lyrics Type | Notes |
|----|--------|-------------|-------|
| 1 | Genius | Plain | Requires `GENIUS_TOKEN` |
| 2 | LRCLIB | Timestamped + Plain | Free, very reliable |
| 3 | YouTube Music | Timestamped + Plain | 3-layer fallback (ytmusicapi → transcript-api → yt-dlp) |
| 4 | NetEase | Timestamped (LRC) | Via syncedlyrics, large catalog |
| 5 | Megalobiz | Timestamped (LRC) | Via syncedlyrics, user-contributed |
| 6 | Musixmatch | Timestamped (LRC) | Via syncedlyrics, optional `MUSIXMATCH_TOKEN` |
| 7 | SimpMusic | Timestamped + Plain | Via api-lyrics.simpmusic.org |

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
# Edit .env and fill in your GENIUS_TOKEN

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

Create a `.env` file in the project root:

```env
# Required for Genius source
GENIUS_TOKEN=your_genius_api_token_here

# Optional
ADMIN_KEY=your_secure_random_key
LOG_LEVEL=INFO
CACHE_TTL=3600
CACHE_DIR=cache

# Optional: path to YouTube Music headers/cookie file
YOUTUBE_COOKIE=path/to/headers.json

# Optional: Musixmatch token (improves results)
MUSIXMATCH_TOKEN=your_musixmatch_token
```

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GENIUS_TOKEN` | No* | — | Genius API token — needed for source 1. Get at [genius.com/api-clients](https://genius.com/api-clients) |
| `ADMIN_KEY` | No | — | Secure key to access admin endpoints (e.g. `/cache/clear`) |
| `LOG_LEVEL` | No | INFO | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `CACHE_TTL` | No | 3600 | Cache time-to-live in seconds |
| `CACHE_DIR` | No | cache | Directory for cache files |
| `YOUTUBE_COOKIE` | No | — | Path to YouTube Music `headers.json` (from ytmusicapi setup) |
| `MUSIXMATCH_TOKEN` | No | — | Musixmatch API token for improved results |

\* Lyrica still works without `GENIUS_TOKEN` — Genius source simply won't load.

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
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho"
```

### With Timestamps
```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho&timestamps=true"
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

### YouTube Music Issues
- Run `ytmusicapi setup` in the project directory
- Set `YOUTUBE_COOKIE` in `.env` to the path of the generated `headers_auth.json`

### Rate Limit Issues
- Wait for the 60-second window to reset
- Cache results in your application to avoid redundant requests

### Port Already in Use
Edit `run.py`:
```python
if __name__ == '__main__':
    app.run(port=8080, debug=True)  # Change 9999 to 8080
```

## 📖 Documentation

- **Full API Reference**: See [USER_GUIDE.md](USER_GUIDE.md)
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

## 🙏 Special Thanks

- **sigma67** — [ytmusicapi](https://github.com/sigma67/ytmusicapi)
- **tranxuanthang & LrcLib Team** — LRC lyrics support
- **maxrave-dev** — SimpMusic integration
- **JioSaavn** — Music metadata and streaming
- **syncedlyrics** — NetEase, Megalobiz, Musixmatch integration
- **MusicBrainz** — Song suggestion/autocomplete data

## 📞 Support

- **Documentation**: [USER_GUIDE.md](USER_GUIDE.md)
- **Issues**: [GitHub Issues](https://github.com/Wilooper/Lyrica/issues)
- **Discussions**: [GitHub Discussions](https://github.com/Wilooper/Lyrica/discussions)
- **Email**: thinkelyorg@gmail.com

---
**Previous Update & Version**: june 06, 2026 & version: 1.2.1

**Latest Updated On**: June 24, 2026 | **Version**: 1.2.10

Made with ❤️ in India 🇮🇳
