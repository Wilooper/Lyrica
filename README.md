# Lyrica — Open Source Lyrics API

> **A high-performance Python/Flask REST API for plain & timestamped lyrics, word-level sync, metadata, sentiment analysis, trending charts, and Groq-powered lyrics translation.**

![Made in India](https://img.shields.io/badge/Made%20in-India-blue.svg)
![Python](https://img.shields.io/badge/Python-3.11%2B-brightgreen.svg)
![Flask](https://img.shields.io/badge/Flask-3.0-blue.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)
![Status](https://img.shields.io/badge/Status-Active-success.svg)

---

## 🆕 What's New

### v1.5.0 (Aug 2026)
- **Apple Music Integration**: Native Apple Music source (ID 8) with syllable-level sync (`&syllabus=true`), word-level sync, and line-level timestamps
- **Syllable-Level Sync**: Per-syllable timing via Apple Music — the most granular sync level for karaoke applications
- **Multi-Sync-Level Fallback**: Intelligent fallback hierarchy: syllable → word → line → plain, automatically degrading to the best available sync level
- **Cache Key v5**: Cache keys now include `syllabus` and `word_level` parameters to prevent collisions across sync levels
- **CI/CD Improvements**: Docker images now auto-published on every push to `main` as `edge` and `sha-*` tags
- **Now on codeberg also**: https://codeberg.org/willooper/Lyrica.git

### v1.4.0
- **Word-Level Sync (Karaoke)**: Per-word timestamps via Lrcmux (`&word=true&timestamps=true`)
- **AI Translation & Romanization**: Real-time lyrics translation and transliteration via Groq LLM
- **Trending Analytics**: Real-time Apple Music top charts by country
- **Song Suggestions**: MusicBrainz-powered autocomplete for search-as-you-type
- **Rate Limiting**: Configurable RPM limits per source with Redis backend support

---

## 📌 Overview

**Lyrica** aggregates song lyrics from **8 active sources** with intelligent sync-level fallback, fast parallel execution, word-level synchronization (Karaoke mode), syllable-level sync, sentiment analysis, song metadata, trending charts, and real-time LLM translation/romanization using Groq.

- 💡 **No API Key Required**: Fully functional out-of-the-box without registration.
- ⚡ **Sub-Second Speed**: Parallel multi-source fetch mode (`fast=true`) with TTL disk caching.
- 🎤 **Word & Syllable-Level Sync**: Per-word and per-syllable timestamps for karaoke applications via Lrcmux (`&word=true`) and Apple Music (`&syllabus=true`).
- 🌐 **AI Translation**: Translate & romanize lyrics on-the-fly via Groq LLM (`&translate=true`).
- 🚀 **Production Ready**: Gunicorn-compatible with multi-key Groq rotation and proxy pool support.

---

## 🚀 Installing / Getting Started

### Quick Start (Local Development)

```bash
# 1. Clone the repository
git clone https://github.com/Wilooper/Lyrica.git
cd Lyrica

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy environment configuration
cp .env.example .env

# 5. Run the server
python run.py
```

Access the server:
- **API Base**: `http://127.0.0.1:9999/`
- **Web Interface (GUI)**: `http://127.0.0.1:9999/app`
- **OpenAPI Spec**: `http://127.0.0.1:9999/openapi.json`

### Docker Quick Start

```bash
# Build & Run Container
docker build -t lyrica .
docker run -p 9999:9999 --env-file .env lyrica
```

---

## ✨ Features

- 🎧 **Multi-Source Aggregation**: 8 active providers with automated sync-level fallback.
- ⏱️ **Synchronized Timestamps (LRC)**: Line-level lyrics timing with millisecond accuracy.
- 🎤 **Word-Level Sync (Karaoke)**: Per-word timing entries via Lrcmux / Apple Music (`&word=true`).
- 🎵 **Syllable-Level Sync**: Per-syllable timing via Apple Music (`&syllabus=true`).
- 🤖 **AI Translation & Romanization**: Real-time translation and transliteration to target languages using Groq LLM (`openai/gpt-oss-120b`).
- 📊 **Sentiment & Mood Analysis**: Polarity, subjectivity, emotion classification, and word frequency breakdown.
- 🖼️ **Rich Track Metadata**: Cover art, duration, genre, release date, and album information.
- 📈 **Trending Charts & Suggestions**: Real-time Apple Music top charts by country and MusicBrainz search autocomplete.
- 🛡️ **Proxy Rotation & Failover**: Thread-safe proxy pool with automated credential masking and cooldowns.
- 💾 **Multi-Tier Caching & Concurrency**: L1 in-memory LRU + L2 Redis + L3 disk-based JSON caching with independent translation caching and high-concurrency async connection pooling.

---

## 🎵 Supported Sources

| ID | Source Name | Lyrics Type | Authentication |
|----|-------------|-------------|----------------|
| 1 | **Genius** | Plain | `GENIUS_TOKEN` (optional) |
| 2 | **LRCLIB** | Timestamped + Plain | None (Free, highly reliable) |
| 3 | **YouTube Music** | Timestamped + Plain | None / Optional Cookies |
| 4 | **NetEase** | Timestamped (LRC) | None |
| 5 | **Megalobiz** | Timestamped (LRC) | None |
| 6 | **Musixmatch** | Timestamped (LRC) | `MUSIXMATCH_TOKEN` (optional) |
| 7 | **Lrcmux** | Timestamped + Word-Level | None (api.lrcmux.dev) |
| 8 | **Apple Music** | Timestamped + Word-Level + Syllable-Level | `APPLE_MUSIC_DEVELOPER_TOKEN` |

*Default Fallback Order:* `LRCLIB (2) → Lrcmux (7) → Genius (1) → YouTube (3) → NetEase (4) → Megalobiz (5) → Musixmatch (6) → Apple Music (8)`
- A new support of apple music will be added soon but if you wants its standalone version then you can access it from below links:-
- [python version](https://github.com/thinkely/LyricaAME-py.git)
- [nextjs version](https://github.com/thinkely/LyricaAME-js.git)

---

## ⚙️ Configuration

Lyrica uses environment variables (`.env`) for secrets and system infrastructure, and `.lyrica.config` for user preferences.

### Environment Variables (`.env`)

```env
ADMIN_KEY=your_secure_admin_key
GENIUS_TOKEN=your_genius_token
GROQ_API_KEY=gsk_key1,gsk_key2
GROQ_MODEL=openai/gpt-oss-120b
REDIS_URL=redis://localhost:6379/0
PROXY_URL=http://user:pass@host:port
APPLE_MUSIC_DEVELOPER_TOKEN=your_apple_music_developer_token
YT_COOKIES_PATH=/app/security/cookies.txt
RATE_LIMIT_STORAGE_URI=memory://
CACHE_TTL=86400
LOG_LEVEL=INFO
```

Detailed environment variable documentation is available in [guide/SETUP_GUIDE.md](guide/SETUP_GUIDE.md).

---

## 📚 Quick API Usage Examples

### 1. Basic Lyrics
```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Coldplay&song=Yellow"
```

### 2. Line-Level Timestamps
```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Coldplay&song=Yellow&timestamps=true"
```

### 3. Word-Level Sync (Karaoke Mode)
```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Coldplay&song=Yellow&timestamps=true&word=true"
```

### 3b. Syllable-Level Sync (Apple Music)
```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Coldplay&song=Yellow&timestamps=true&syllabus=true"
```

### 4. Translation & Romanization (Groq LLM)
```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Karan%20Aujla&song=Boyfriend&timestamps=true&translate=true&romanize=true&language=en"
```

### 5. Mood Analysis & Metadata (Fast Mode)
```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho&fast=true&mood=true&metadata=true"
```

### 6. Song Suggestions (Autocomplete)
```bash
curl "http://127.0.0.1:9999/suggestion?q=Tum%20Hi%20Ho&limit=5"
```

### 7. Trending Songs (India)
```bash
curl "http://127.0.0.1:9999/trending/?country=IN&limit=10"
```

---

## 🚀 Deployment

Lyrica is production-ready for deployment on VPS, Docker, Render, Hugging Face, Railway, Fly.io, Vercel, and cloud providers.

```bash
# Example Production Startup via Gunicorn
gunicorn -w 4 -b 0.0.0.0:9999 --timeout 120 run:app
```

📖 **For complete deployment guides (Docker, Nginx + SSL, Cloud Hosts), see [guide/DEPLOYMENT_GUIDE.md](guide/DEPLOYMENT_GUIDE.md).**

---

## 📖 Detailed Guides & Documentation

Explore dedicated guides in the [`guide/`](guide/) directory:

- 🚀 [**Setup & Installation Guide**](guide/SETUP_GUIDE.md) — Local setup, environment variables, user config.
- 📖 [**Complete API & User Reference**](guide/USER_GUIDE.md) — Full endpoint reference, query parameters, schemas.
- 🎤 [**Word-Level Sync (Karaoke) Guide**](guide/WORD_SYNC_GUIDE.md) — Timestamps schema and integration examples.
- 🌐 [**Lyrics Translation Guide**](guide/TRANSLATION_GUIDE.md) — Groq LLM setup, multi-key rotation, language options.
- 🚢 [**Production Deployment Guide**](guide/DEPLOYMENT_GUIDE.md) — Deployment instructions for Docker, VPS, Render, HF, Railway, Fly.io, Vercel.

---

## 🛠️ Troubleshooting

- **No Lyrics Found**: Verify song title and artist spelling. Try `fast=true` to query sources in parallel.
- **YouTube Cloud IP Blocking**: Set `PROXY_URL` or `YT_PROXY_URL` in `.env` to route requests through proxy servers.
- **Groq API Rate Limits**: Supply multiple Groq keys in `GROQ_API_KEY` (comma-separated) for round-robin rotation.
- **Port Busy**: Modify port in `run.py` or specify `-b 0.0.0.0:<PORT>` when starting Gunicorn.

---

## 🤝 Contributing

Contributions are warmly welcome!

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m 'Add amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

Please ensure code adheres to PEP 8 standards and new features include documentation updates.

---

## 👥 Contributors

<!-- readme: contributors -start -->
<table>
	<tbody>
		<tr>
            <td align="center">
                <a href="https://github.com/thinkely">
                    <img src="https://avatars.githubusercontent.com/u/321372956?v=4" width="100;" alt="thinkely"/>
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
                    <sub><b>Shelbee Johnson</b></sub>
                </a>
            </td>
		</tr>
	<tbody>
</table>
<!-- readme: contributors -end -->

---

## 🙏 Special Thanks

- **sigma67** — [ytmusicapi](https://github.com/sigma67/ytmusicapi)
- **LrcLib Team** — Synchronized lyrics provider
- **Lrcmux Team** — Musixmatch lyrics aggregation via [api.lrcmux.dev](https://api.lrcmux.dev)
- **Groq** — High-speed LLM inference
- **JioSaavn** — Metadata & audio integration
- **syncedlyrics** — NetEase, Megalobiz, Musixmatch fetcher integration

---

## 📝 License

Licensed under the [MIT License](LICENSE) © 2026 Lyrica Contributors.

Made with ❤️ in India 🇮🇳
