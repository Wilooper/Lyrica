# 🎵 Lyrica API — Setup & Getting Started Guide

Welcome to **Lyrica**! This guide covers everything you need to set up, configure, and run the Lyrica REST API locally or on your server.

---

## 📋 Prerequisites

Before setting up Lyrica, make sure you have the following installed:
- **Python**: 3.11 or higher (3.12 recommended)
- **Git**: For cloning the repository
- **pip**: Python package manager
- **(Optional) Docker**: For containerized deployment

---

## 🚀 Quick Start (Local Setup)

### 1. Clone the Repository

```bash
git clone https://github.com/Wilooper/Lyrica.git
cd Lyrica
```

### 2. Create a Virtual Environment

```bash
# On Linux / macOS
python3 -m venv venv
source venv/bin/activate

# On Windows (PowerShell)
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Copy the example `.env` file:

```bash
cp .env.example .env
```

Open `.env` in your text editor and configure your secrets (see [Environment Variables Reference](#environment-variables-reference) below).

### 5. Start the Server

```bash
python run.py
```

The server will start at `http://127.0.0.1:9999` by default.

---

## 🌐 Verifying Your Setup

Once the server is running, test these URLs in your browser or terminal:

| URL | Description |
|-----|-------------|
| `http://127.0.0.1:9999/` | API Information and health status |
| `http://127.0.0.1:9999/app` | Web GUI for testing lyrics, translations, and mood analysis |
| `http://127.0.0.1:9999/openapi.json` | OpenAPI 3.0 specification |
| `http://127.0.0.1:9999/lyrics/?artist=Coldplay&song=Yellow` | Basic lyrics endpoint test |

---

## 🔑 Key Configurations

### 1. Environment Variables Reference (`.env`)

| Variable | Required? | Default | Description |
|----------|-----------|---------|-------------|
| `ADMIN_KEY` | Recommended | — | Key to protect `/cache/clear`, `/config/reload`, and `/proxy/*` admin endpoints |
| `GENIUS_TOKEN` | Optional | — | Client access token for Genius (Source 1) |
| `MUSIXMATCH_TOKEN` | Optional | — | Client access token for Musixmatch (Source 6) |
| `APPLE_MUSIC_DEVELOPER_TOKEN` | Optional | — | Apple Music Developer JWT token for lyric fetching (Source 8). Also accepts `DEVELOPER_TOKEN` as alias. |
| `APPLE_MUSIC_USER_TOKEN` | Optional | — | Apple Music user authentication token (may be required for some API endpoints). Also accepts `MUSIC_USER_TOKEN` as alias. |
| `APPLE_STOREFRONT` | Optional | `us` | Apple Music storefront country code (e.g., `us`, `gb`, `in`). |
| `APPLE_LYRICS_LANGUAGE` | Optional | `en` | Preferred lyrics language code. |
| `APPLE_LYRICS_SCRIPT` | Optional | `latin` | Preferred lyrics script code. |
| `GROQ_API_KEY` | Optional | — | Groq LLM key(s) for lyrics translation & romanization. Supports comma-separated keys for round-robin load balancing |
| `GROQ_MODEL` | Optional | `openai/gpt-oss-120b` | Override Groq LLM model (default: `openai/gpt-oss-120b`) |
| `REDIS_URL` | Optional | — | Redis connection URL for L2 distributed cache and shared rate limiting (e.g. `redis://localhost:6379/0`) |
| `PROXY_URL` | Optional | — | Global proxy URL or comma-separated proxy list for all fetchers |
| `YT_PROXY_URL` | Optional | — | Dedicated proxy URL for YouTube Music fetcher |
| `YT_COOKIES_PATH` | Optional | — | Absolute path to `cookies.txt` (used by YouTube fetcher layer 3) |
| `YT_HEADERS_PATH` | Optional | — | Absolute path to `headers_auth.json` (used by YouTube fetcher layer 1) |
| `LRCMUX_API_URL` | Optional | `https://api.lrcmux.dev` | Lrcmux base API URL |
| `LRCLIB_API_URL` | Optional | `https://lrclib.net` | LRCLIB base API URL |
| `RATE_LIMIT_STORAGE_URI` | Optional | `memory://` | Storage backend for rate limiter (defaults to `REDIS_URL` if set, or `memory://`) |

| `LOG_LEVEL` | Optional | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `CACHE_TTL` | Optional | `86400` | Caching TTL in seconds (default: 24 hours) |
| `CACHE_DIR` | Optional | `cache_data` | Directory path for file-based JSON cache |

### 2. Genius API Setup (Optional - Source 1)

1. Register or log in at [Genius API Clients](https://genius.com/api-clients).
2. Click **New API Client**, fill in details, and save.
3. Copy the **Client Access Token**.
4. Set in `.env`: `GENIUS_TOKEN=your_genius_token_here`

### 3. Groq LLM Setup (Optional - Translation & Romanization)

1. Sign up at [Groq Console](https://console.groq.com/).
2. Generate an API Key under **API Keys**.
3. Set in `.env`: `GROQ_API_KEY=gsk_your_groq_api_key`
4. Multiple keys can be provided separated by commas for load balancing: `GROQ_API_KEY=gsk_key1,gsk_key2`

### 4. YouTube Auth & Cookies Setup (Optional)

If running in hosted environments where YouTube blocks data center IPs:
1. Export YouTube cookies from your browser to a `cookies.txt` file (using extensions like *Get cookies.txt LOCALLY*).
2. Set `YT_COOKIES_PATH=/path/to/cookies.txt` in `.env`.
3. Alternatively, export `headers_auth.json` via `ytmusicapi` and set `YT_HEADERS_PATH=/path/to/headers_auth.json`.

### 5.1 Musixmatch Token (Optional - Source 6)
1. Sign up at [Musixmatch Developer](https://developer.musixmatch.com/).
2. Create a new app and obtain your API key.
3. Set in `.env`: `MUSIXMATCH_TOKEN=your_musixmatch_token_here`

### 6. Apple Music Developer Token (Optional - Source 8)

Apple Music provides the highest-quality synchronized lyrics with **syllable-level** and **word-level** timing. To enable this source:

1. Enroll in the [Apple Developer Program](https://developer.apple.com/programs/) ($99/year).
2. Create a new **MusicKit App** in [App Store Connect](https://appstoreconnect.apple.com/).
3. Generate a **Provider Token** (JWT) with the following claims:
   - `iss`: Your Team ID
   - `iat`: Issue timestamp
   - `exp`: Expiration (max 20 minutes from `iat`)
   - `nonce`: Unique UUID
4. Set in `.env`:
   ```env
   APPLE_MUSIC_DEVELOPER_TOKEN=your_jwt_here
   APPLE_MUSIC_USER_TOKEN=your_user_token_if_available  # optional
   APPLE_STOREFRONT=us                                 # optional, default: us
   APPLE_LYRICS_LANGUAGE=en                              # optional, default: en
   APPLE_LYRICS_SCRIPT=latin                             # optional, default: latin
   ```
5. Request syllable-level sync: `/lyrics/?artist=...&song=...&timestamps=true&syllabus=true`
6. Request word-level sync: `/lyrics/?artist=...&song=...&timestamps=true&word=true`

> [!IMPORTANT]
> Without `APPLE_MUSIC_DEVELOPER_TOKEN`, the Apple Music fetcher is entirely disabled and will never be queried.

### 7. User Configuration File (`.lyrica.config`)

To customize fetcher defaults, rate limits, or static proxy lists without modifying code:

```bash
cp .lyrica.config.example .lyrica.config
```

Example `.lyrica.config`:

```ini
[defaults]
fast = false
timestamps = false
word = false
mood = false
metadata = false
translate = false
romanize = false
language = en
sequence = 2,7,1,3,4,5,6

[rate_limits]
genius_rpm = 60
lrclib_rpm = 120
youtube_rpm = 30
netease_rpm = 60
megalobiz_rpm = 60
musixmatch_rpm = 30
lrcmux_rpm = 60
apple_music_rpm = 60

[proxies]
# Add proxies for round-robin rotation if needed
# proxy_1 = http://user:pass@1.2.3.4:8080
# proxy_2 = socks5://5.6.7.8:1080
```

---

## 🎵 Source Registry

Lyrica queries sources in order until lyrics are found:

| ID | Name | Source | Supported Sync | Authentication |
|----|------|--------|----------------|----------------|
| 1 | `genius` | Genius.com | Plain | `GENIUS_TOKEN` (optional) |
| 2 | `lrclib` | LRCLIB | Line-level & Plain | None (Free) |
| 3 | `youtube` | YouTube Music | Line-level & Plain | None / Optional Cookies |
| 4 | `netease` | NetEase Cloud Music | Line-level (LRC) | None |
| 5 | `megalobiz` | Megalobiz | Line-level (LRC) | None |
| 6 | `musixmatch` | Musixmatch | Line-level (LRC) | `MUSIXMATCH_TOKEN` (optional) |
| 7 | `lrcmux` | Lrcmux (api.lrcmux.dev) | Line-level & Word-level | None |
| 8 | `apple_music` | Apple Music | Line, Word-level & Syllable-level | `APPLE_MUSIC_DEVELOPER_TOKEN` |

---

## 🛠️ Port & Host Customization

If port `9999` is already in use, you can edit [run.py](file:///c:/Users/62atu/New%20folder/Lyrica/run.py):

```python
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
```

Or run via Gunicorn:

```bash
gunicorn -w 4 -b 0.0.0.0:8080 run:app
```

---

## 📖 Next Steps

- Check out the full API specification in [USER_GUIDE.md](file:///c:/Users/62atu/New%20folder/Lyrica/guide/USER_GUIDE.md).
- Learn about Karaoke per-word lyrics in [WORD_SYNC_GUIDE.md](file:///c:/Users/62atu/New%20folder/Lyrica/guide/WORD_SYNC_GUIDE.md).
- Configure lyrics translation & romanization in [TRANSLATION_GUIDE.md](file:///c:/Users/62atu/New%20folder/Lyrica/guide/TRANSLATION_GUIDE.md).
- Deploy to cloud or VPS using [DEPLOYMENT_GUIDE.md](file:///c:/Users/62atu/New%20folder/Lyrica/guide/DEPLOYMENT_GUIDE.md).
