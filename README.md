# Lyrica - Open Source Lyrics API

![Made in India](https://img.shields.io/badge/Made%20in-India-blue.svg) ![Python](https://img.shields.io/badge/Python-3.12%2B-brightgreen.svg) ![License](https://img.shields.io/badge/License-MIT-yellow.svg) ![Flask](https://img.shields.io/badge/Flask-3.0.0-blue.svg) ![Status](https://img.shields.io/badge/Status-Active-success.svg)

A powerful, open-source RESTful API for retrieving song lyrics with advanced features like mood analysis, timestamped lyrics, metadata extraction, and multi-source aggregation. Built with Python and Flask, optimized for Bollywood and global music queries.

## ✨ Key Features

- **Multi-Source Lyrics Retrieval** - Aggregates from 6 premium sources with intelligent fallback
- **Timestamped Lyrics (LRC)** - Synchronized lyrics with millisecond precision from YouTube Music and LrcLib
- **Mood & Sentiment Analysis** - AI-powered sentiment detection and word frequency analysis
- **Rich Metadata** - Song cover art, duration, genre, release date, and artist info
- **Smart Caching** - TTL-based caching (5 min default) to reduce external API calls
- **Rate Limiting** - 15 requests/minute per IP with Redis support for distributed systems
- **Fast Mode** - Parallel fetching for sub-second response times
- **CORS-Enabled** - Production-ready for frontend integration
- **Interactive GUI** - Built-in web interface for testing and exploration
- **Admin Tools** - Cache management and statistics endpoints
- **Comprehensive Logging** - Debug and monitor with detailed request/response logs
- **Made in India** 🇮🇳 - Optimized for Indian music platforms (JioSaavn integration)

## What's New:-
- Added a trending endpoint so so you can access top trending content of any country using apple music
- Added top querry endpoint so you can get user top querries in your server

## 🎵 Supported Sources

| ID | Source | Lyrics Type | Speed |
|----|--------|-------------|-------|
| 1 | Genius | Plain | Medium |
| 2 | LRCLIB | Timestamped | Slow |
| 3 | SimpMusic | Plain | Fast |
| 4 | YouTube Music | Timestamped | Medium |
| 5 | Lyrics.ovh | Plain | Fast |
| 6 | ChartLyrics | Plain | Fast |

## 📦 Installation

### Prerequisites
- Python 3.12 or higher
- pip (Python package manager)
- Git
- Redis (optional, for production rate limiting)

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
cat > .env << EOF
GENIUS_TOKEN=your_genius_api_token
ADMIN_KEY=your_secure_admin_key
LOG_LEVEL=INFO
CACHE_TTL=300
EOF

# 5. Run the server
python run.py
```

Access the API at: `http://127.0.0.1:9999`
- Web GUI: `http://127.0.0.1:9999/app`
- API Docs: `http://127.0.0.1:9999/`

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
# Required
GENIUS_TOKEN=your_genius_api_token_here

# Optional but recommended
ADMIN_KEY=your_secure_random_key
LOG_LEVEL=INFO
CACHE_TTL=300
RATE_LIMIT_STORAGE_URI=memory://
YOUTUBE_COOKIE=path/to/headers.json

# Production
RATE_LIMIT_STORAGE_URI=redis://localhost:6379/0
```

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GENIUS_TOKEN` | Yes | - | Genius API token from [genius.com/api-clients](https://genius.com/api-clients) |
| `ADMIN_KEY` | No | - | Secure key for admin endpoints |
| `LOG_LEVEL` | No | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `CACHE_TTL` | No | 300 | Cache time-to-live in seconds |
| `RATE_LIMIT_STORAGE_URI` | No | memory:// | memory:// or redis://host:port/db |
| `YOUTUBE_COOKIE` | No | - | Path to YouTube headers.json (rename from ytmusicapi) |

## 🚀 Deployment

### Render.com
1. Push repository to GitHub
2. Create new Web Service on Render
3. Set build command: `pip install -r requirements.txt`
4. Set start command: `gunicorn -w 4 -b 0.0.0.0:9999 run:app`
5. Add environment variables in dashboard
6. Deploy

### Heroku
```bash
heroku create lyrica-api
heroku config:set GENIUS_TOKEN=your_token
git push heroku main
```

### Self-Hosted (Gunicorn + Nginx)
```bash
# Install Gunicorn
pip install gunicorn

# Run with 4 workers
gunicorn -w 4 -b 127.0.0.1:9999 --timeout 120 run:app

# Configure Nginx as reverse proxy
# See deployment guides for full setup
```
## NOTE:-
- If you don't want to self host or run this project in local host you can use the following link to use prehosted server all endpoints will same as they are in local host
- LINK:- https://test-0k.onrender.com
## 📚 Quick API Examples

### Basic Lyrics Request
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

## 🛠️ Troubleshooting

### No Lyrics Found
- Verify artist and song names are exact
- Check internet connection
- Review server logs: `tail -f logs/app.log`
- Try popular songs first

### Genius API Errors
- Regenerate token at [genius.com/api-clients](https://genius.com/api-clients)
- Verify token in `.env`
- Check token hasn't expired

### YouTube Music Auth Issues
- Run `ytmusicapi setup` in project directory
- Rename generated `headers.json` to match `YOUTUBE_COOKIE` path
- Verify file has proper authentication data

### Rate Limit Issues
- Switch to Redis backend: `RATE_LIMIT_STORAGE_URI=redis://...`
- Increase rate limit in configuration
- Wait for 60-second window to reset

### Port Already in Use
Edit `run.py`:
```python
if __name__ == '__main__':
    app.run(port=8080, debug=True)  # Change 9999 to 8080
```

## 📖 Documentation

- **Full API Documentation**: See [USER_GUIDE.md](USER_GUIDE.md)
- **Swagger/OpenAPI Spec**: Available at `/swagger` endpoint
- **Examples**: Check `/examples` directory in repository
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
- All tests pass
- Documentation is updated
- Commit messages are descriptive

## 📝 License

MIT License © 2025 Lyrica Contributors

See [LICENSE](LICENSE) file for details.

## 🙏 Special Thanks

- **sigma67** - [ytmusicapi](https://github.com/sigma67/ytmusicapi)
- **tranxuanthang & LrcLib Team** - LRC lyrics support
- **maxrave-dev** - Simp Music integration
- **JioSaavn API** - Music metadata and streaming

## 📞 Support

- **Documentation**: [USER_GUIDE.md](USER_GUIDE.md)
- **Issues**: [GitHub Issues](https://github.com/Wilooper/Lyrica/issues)
- **Discussions**: [GitHub Discussions](https://github.com/Wilooper/Lyrica/discussions)
- **Email**: thinkelyorg@gmail.com

---

**Last Updated**: January 19, 2026 | **Version**: 1.2.0

Made with ❤️ in India 🇮🇳
