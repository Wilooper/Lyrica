# 🎵 Lyrica API — Setup Guide

Welcome to Lyrica! This guide covers everything you need to get the server running and start using the API.

---

## 🚀 Quick Start

### 1. Clone and Install

```bash
git clone https://github.com/Wilooper/Lyrica.git
cd Lyrica

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate       # Linux / macOS
venv\Scripts\activate          # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Open `.env` and fill in your values:

```env
# Required for Genius source (source 1)
GENIUS_TOKEN=your_genius_api_token_here

# Optional — secures the /cache/clear admin endpoint
ADMIN_KEY=your_secure_random_key

# Optional
LOG_LEVEL=INFO
CACHE_TTL=3600
CACHE_DIR=cache

# Optional — path to YouTube Music headers file
YOUTUBE_COOKIE=path/to/headers_auth.json

# Optional — improves Musixmatch results
MUSIXMATCH_TOKEN=your_musixmatch_token
```

### 3. Start the Server

```bash
python run.py
```

The server will start at `http://127.0.0.1:9999`.

| URL | Description |
|-----|-------------|
| `http://127.0.0.1:9999/` | API info and endpoint list |
| `http://127.0.0.1:9999/app` | Web GUI (test the API in your browser) |
| `http://127.0.0.1:9999/lyrics/?artist=...&song=...` | Fetch lyrics |

---

## 🎯 How to Use the API

### Basic Lyrics Search

```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho"
```

### With Timestamped Lyrics (karaoke mode)

```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho&timestamps=true"
```

### Trending Songs

```bash
# India top 10
curl "http://127.0.0.1:9999/trending/?country=IN&limit=10"

# Multiple countries
curl "http://127.0.0.1:9999/trending/?countries=US,IN,GB&limit=5"
```

### Song Autocomplete / Suggestions

```bash
curl "http://127.0.0.1:9999/suggestion?q=Tum%20Hi%20Ho&limit=5"
```

### Using the Web GUI

1. Navigate to `http://127.0.0.1:9999/app`
2. Enter an **Artist** name and **Song** title
3. Toggle options (timestamps, mood, metadata)
4. Click **Find Lyrics**

---

## 🎪 Sample Songs to Try

| Artist | Song | Why |
|--------|------|-----|
| Arijit Singh | Tum Hi Ho | Popular Bollywood — reliable across all sources |
| The Weeknd | Blinding Lights | English — great for timestamp testing |
| Yo Yo Honey Singh | Blue Eyes | Hindi — good karaoke song |
| Shreya Ghoshal | Teri Ore | Synchronized lyrics available |
| Taylor Swift | Shake It Off | English — Musixmatch/Genius coverage |

---

## 🎵 Active Sources

| ID | Source | Notes |
|----|--------|-------|
| 1 | Genius | Requires `GENIUS_TOKEN` |
| 2 | LRCLIB | Free, highly reliable |
| 3 | YouTube Music | Best timestamped quality |
| 4 | NetEase | Large catalog, LRC |
| 5 | Megalobiz | User-contributed LRC |
| 6 | Musixmatch | Optional token improves results |
| 7 | SimpMusic | Fast, good coverage |

> Lyrics.ovh, ChartLyrics, and LyricsFreek have been removed — these APIs are no longer operational.

---

## 🔧 Optional Integrations

### Genius API Token

Get a free token at https://genius.com/api-clients:

1. Create / log in to your Genius account
2. Go to **API Clients** → **New API Client**
3. Copy the **Client Access Token**
4. Add to `.env`: `GENIUS_TOKEN=your_token`

### YouTube Music Auth (Optional)

For better YouTube Music results:

```bash
pip install ytmusicapi
ytmusicapi setup
# Follow the browser-based setup to generate headers_auth.json
```

Then set `YOUTUBE_COOKIE=path/to/headers_auth.json` in `.env`.

### Musixmatch Token (Optional)

Register at https://developer.musixmatch.com/ and add:
```env
MUSIXMATCH_TOKEN=your_token
```

---

## 🚀 Production Deployment

### Gunicorn

```bash
gunicorn -w 4 -b 0.0.0.0:9999 --timeout 120 run:app
```

### Render.com

1. Push the repo to GitHub
2. Create a new Web Service on Render
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn -w 4 -b 0.0.0.0:9999 run:app`
5. Add environment variables in the Render dashboard
6. Deploy

### Docker

```bash
docker build -t lyrica .
docker run -p 9999:9999 \
  -e GENIUS_TOKEN=your_token \
  -e ADMIN_KEY=your_key \
  lyrica
```

### Pre-hosted Servers

If you don't want to self-host:

| Server | URL | Notes |
|--------|-----|-------|
| Render | https://test-0k.onrender.com | May have cold-start delays |
| Hugging Face | https://wilooper-lyrica.hf.space | **Recommended for production** — ~95% uptime, high concurrency |

---

## 🐛 Troubleshooting

### Server Won't Start

```bash
# Check Python version (needs 3.12+)
python --version

# Reinstall dependencies
pip install -r requirements.txt
```

### No Lyrics Found

- Check artist/song spelling
- Try a popular song to verify internet connectivity
- Add `&fast=true` to race multiple sources in parallel

### Genius Not Working

- Verify `GENIUS_TOKEN` is set in `.env`
- Regenerate at https://genius.com/api-clients
- The API still works without it — 6 other sources remain active

### YouTube Music Issues

- Run `ytmusicapi setup` and update `YOUTUBE_COOKIE` in `.env`
- If not configured, the 3-layer fallback (transcript-api → yt-dlp) still works without auth

### Port Already in Use

Edit `run.py` and change the port:

```python
if __name__ == '__main__':
    app.run(port=8080, debug=True)
```

### CORS Issues in Browser

The API includes CORS headers by default. If you're still hitting issues:

- Serve your frontend from a proper local server (`python -m http.server 8000`)
- Verify the request URL matches the running server port

---

## 📖 More Documentation

- **Full API Reference**: [USER_GUIDE.md](USER_GUIDE.md)
- **Project README**: [README.md](README.md)
- **Issues & Feature Requests**: [GitHub Issues](https://github.com/Wilooper/Lyrica/issues)

---

**Happy building! 🎵**
*Made with ❤️ in India 🇮🇳*