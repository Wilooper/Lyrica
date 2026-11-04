# Lyrica

<p align="center">
  <img src="static/banner.jpg" alt="Lyrica Banner" width="600" onerror="this.style.display='none'"/>
</p>

<p align="center">
  <strong>High-performance, multi-provider lyrics aggregation API for plain, synchronized (LRC), word-level, and syllable-level lyrics with real-time AI translation.</strong>
</p>

<p align="center">
  <a href="https://github.com/Wilooper/Lyrica/actions/workflows/publish.yml"><img src="https://img.shields.io/github/actions/workflow/status/Wilooper/Lyrica/publish.yml?branch=main&label=CI%2FCD&logo=github" alt="CI/CD Status"></a>
  <a href="https://github.com/Wilooper/Lyrica/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-brightgreen.svg?logo=python" alt="Python Versions">
  <img src="https://img.shields.io/badge/docker-ready-2496ED.svg?logo=docker&logoColor=white" alt="Docker Ready">
  <a href="https://wilooper.github.io/Lyrica/"><img src="https://img.shields.io/badge/docs-MkDocs%20Material-526CFE.svg?logo=materialformkdocs&logoColor=white" alt="Documentation"></a>
  <img src="https://img.shields.io/badge/release-v2--beta--rollout-orange.svg" alt="Release: v2-beta-rollout">
</p>

> [!IMPORTANT]
> This is the **v2-beta-rollout** beta release. The existing v1 API at
> `/lyrics/` is unchanged; new clients should use `/v2/lyrics`. See
> [the release notes](docs/release-notes/v2-beta-rollout.md) for test results,
> performance matrices, and known limitations.

---

## 📌 Overview

**Lyrica** aggregates song lyrics across **5 zero-config sources** plus **2 token-gated sources** with intelligent multi-sync degradation, sub-millisecond multi-tier caching (68k+ L1 lookups/sec in the release benchmark), and real-time neural translation/romanization powered by Groq LLMs (`openai/gpt-oss-120b`). YouTube Music is temporarily disabled while its fetcher is rebuilt.

Whether you are building a **karaoke player**, a **music streaming client**, an **accessibility read-along tool**, or a **music discovery platform**, Lyrica delivers consistent, structured JSON responses with zero mandatory configuration.

### ✨ Key Features

- 🎵 **Multi-Provider Aggregation**: Zero-config fallback across LRCLIB, Lrcmux, Genius, NetEase, and Megalobiz. Apple Music and Musixmatch are loaded only when their tokens are configured. YouTube Music is temporarily disabled.
- ✅ **Verified Results**: Every provider response is scored for title, artist, duration, content sanity, and LRC validity before it can be served or cached. Wrong-song results are rejected.
- 🧠 **Canonical Caching**: One fetch per song, not one per flag combination. Raw lyrics are cached at their richest tier and derived down on demand; concurrent misses are coalesced with singleflight and confirmed absences use a short negative cache.
- 🛡️ **Provider Safety**: Per-provider token buckets, circuit breakers, bulkheads, and live latency/error metrics at `/v2/health`.
- 📦 **Lean v2 API**: `/v2/lyrics` returns compact `[start_ms, text]` lines (about 60% smaller than v1) with ETag/304 support. The v1 endpoint `/lyrics/` is unchanged.
- ⏱️ **Multi-Granular Synchronization**:
  - **Line-Level (LRC)**: Sentence-by-sentence millisecond timing (`&timestamps=true`).
  - **Word-Level (Karaoke)**: Per-word start and end timing for real-time highlighting (`&word=true`). Word-sync requests are routed only to Lrcmux and Apple Music.
  - **Syllable-Level**: Sub-word vocal syllable timing via Apple Music AMP API (`&syllabus=true`). Syllable requests use Apple Music first, then Lrcmux.
- 🤖 **AI Translation & Romanization**: Real-time lyrics translation and script transliteration via Groq LLMs.
- ⚡ **68,000+ L1 Lookups/sec**: Multi-tier cache architecture (L1 In-Memory LRU + L2 Redis + L3 Disk) ensures sub-millisecond latency on cache hits, as measured in the v2-beta-rollout release benchmark.
- 📊 **Track Intelligence**: Integrated mood analysis, emotional polarity, and rich metadata (cover art, genre, release date).
- 🛡️ **Production-Hardened**: Gunicorn `gevent` concurrency (2,000+ conns/worker), unprivileged Docker user, `tini` PID 1, and health checks.

---

## 🚀 Quick Start

### 1. Run with Docker Compose (Recommended)

The fastest way to run Lyrica with full L2 Redis distributed caching:

```bash
git clone https://github.com/Wilooper/Lyrica.git
cd Lyrica
cp .env.example .env
docker compose up -d
```

The API is instantly live at **`http://localhost:7860/`**.

### 2. Run Locally with Python

```bash
git clone https://github.com/Wilooper/Lyrica.git
cd Lyrica
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

The API is live at **`http://127.0.0.1:9999/`**.

---

## 💡 Verified API Examples

### 1. Fetch Plain Lyrics
```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Coldplay&song=Yellow"
```

```json
{
  "status": "success",
  "data": {
    "source": "lrclib",
    "artist": "Coldplay",
    "title": "Yellow",
    "hasTimestamps": false,
    "lyrics": "Look at the stars\nLook how they shine for you..."
  }
}
```

### 2. Synchronized Line-Level Lyrics (LRC)
```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Coldplay&song=Yellow&timestamps=true"
```

```json
{
  "status": "success",
  "data": {
    "source": "lrclib",
    "artist": "Coldplay",
    "title": "Yellow",
    "sync_level": "line",
    "hasTimestamps": true,
    "timed_lyrics": [
      { "id": "lrc_0", "text": "Look at the stars", "start_time": 36189, "end_time": 37719 }
    ]
  }
}
```

### 3. Word-Level Sync (Karaoke Mode)
```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Coldplay&song=Yellow&timestamps=true&word=true"
```

Word requests are routed only to Lrcmux and Apple Music. Availability depends
on the track; if neither has word timing, v1 returns the best line/plain
result from those providers.

```json
{
  "status": "success",
  "data": {
    "source": "lrcmux",
    "artist": "Coldplay",
    "title": "Yellow",
    "sync_level": "word",
    "hasTimestamps": true,
    "timed_lyrics": [
      {
        "id": "lrc_0",
        "text": "Look at the stars",
        "start_time": 36189,
        "end_time": 37719,
        "words": [
          { "word": "Look", "start": 36189, "end": 36520 },
          { "word": "at", "start": 36520, "end": 36800 },
          { "word": "the", "start": 36800, "end": 37050 },
          { "word": "stars", "start": 37050, "end": 37719 }
        ]
      }
    ]
  }
}
```

### 4. Real-Time Translation & Romanization (Groq LLM)
```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Karan%20Aujla&song=Boyfriend&timestamps=true&translate=true&romanize=true&language=en"
```

### 5. Song Autocomplete & Suggestions
```bash
curl "http://127.0.0.1:9999/suggestion?q=Bohemian%20Rhapsody&limit=3"
```

### 6. Lean v2 Lyrics (recommended for new clients)
```bash
curl "http://127.0.0.1:9999/v2/lyrics?artist=Coldplay&song=Yellow&tier=line"
```

```json
{
  "v": 2,
  "src": "lrclib",
  "tier": "line",
  "artist": "Coldplay",
  "title": "Yellow",
  "dur": 267000,
  "lines": [[35660, "Look at the stars"], [38460, "Look how they shine for you"]]
}
```

`tier` accepts `plain`, `line`, `word`, or `syllable`. Responses carry an
`ETag`; send it back as `If-None-Match` for a bodyless `304`. See
[the v2 API docs](docs/api/v2.md), [the v2-beta-rollout release notes](docs/release-notes/v2-beta-rollout.md), and `/v2/health` for provider state.

---

## 🏗️ Architecture Overview

```mermaid
graph LR
    Client([Client Application]) --> Router[Flask REST API]
    Router --> Cache{L1/L2/L3 Cache}
    Cache -- Hit (0.003ms) --> Client
    Cache -- Miss --> Controller[Fetch Controller]
    Controller --> P1[LRCLIB]
    Controller --> P2[Lrcmux]
    Controller --> P3[Genius]
    Controller --> P4[Apple Music]
    Controller --> P5[NetEase / Megalobiz]
    Controller --> LLM[Groq AI Processor]
    Controller --> SaveCache[Multi-Tier Cache Save]
    SaveCache --> Client
```

---

## 🎵 Provider Registry

| ID | Provider | Lyrics Type | Sync Capabilities | Authentication |
|:---:|---|---|---|---|
| **1** | **Genius** | Plain | Complete Verses (Depth-Tracking) | None needed (Public Web Search fallback) or `GENIUS_TOKEN` |
| **2** | **LRCLIB** | Timestamped + Plain | Line-Level | Free, no token required |
| **3** | **YouTube Music** | — | — | Temporarily disabled (fetcher being rebuilt) |
| **4** | **NetEase** | Timestamped | Line-Level | Free |
| **5** | **Megalobiz** | Timestamped | Line-Level | Free |
| **6** | **Musixmatch** | Timestamped | Line-Level | `MUSIXMATCH_TOKEN` (required to load) |
| **7** | **Lrcmux** | Timestamped + Word-Level | Line & Word | Free via `api.lrcmux.dev` |
| **8** | **Apple Music** | Timestamped + Word + Syllable | Line, Word & Syllable | `APPLE_MUSIC_DEVELOPER_TOKEN` (required to load) |

*Default Fallback Sequence:* `LRCLIB (2) → Lrcmux (7) → Genius (1) → NetEase (4) → Megalobiz (5) → Musixmatch (6) → Apple Music (8)`

Providers that require a token are omitted from the sequence when the token is not configured. For `word=true` or `syllabus=true`, automatic routing is restricted to Lrcmux and Apple Music.

---

## 📚 Complete Documentation

Full, structured documentation is available in the [`docs/`](docs/) directory and online:

- 🚀 [**Getting Started & Installation**](docs/getting-started/quickstart.md) — Prerequisites, virtualenv, and configuration.
- 📖 [**API Reference Guide**](docs/api/overview.md) — Comprehensive parameter and endpoint reference.
- 🎤 [**Word & Syllable Sync Guide**](docs/api/lyrics.md#synchronization-levels) — Integration guide for karaoke and rhythm apps.
- 🏛️ [**Architecture & Caching**](docs/architecture/caching.md) — In-memory LRU, Redis, and disk caching mechanics.
- 🚢 [**Deployment Guide**](docs/deployment/docker.md) — Docker Compose, VPS (Nginx + SSL), Render, Hugging Face, and Vercel.
- 🧪 [**Testing & Benchmarks**](docs/development/testing.md) — Automated test suite and concurrency benchmarks.

---

## 🧪 Testing & Verification

Lyrica includes an end-to-end automated test harness:

```bash
# Run all unit, live integration, and performance benchmarks
python Test/run_all_tests.py
```

Results:
- **Genius Parser Unit Tests**: Verified depth-tracking parsing without missing verses.
- **Live Integration Tests**: Live requests against real Genius servers (`The Weeknd`, `Queen`).
- **Performance Benchmark**: **68,624 req/s** on the L1 cache and **3,266 req/s** on concurrent Flask test-client routes. See the [release notes](docs/release-notes/v2-beta-rollout.md) for full matrices and benchmark caveats.

---

## 🤝 Contributing & Community

Contributions are warmly welcomed! Please read our [Contributing Guide](docs/development/contributing.md) and [Code of Conduct](CODE_OF_CONDUCT.md) before submitting a Pull Request.

<!-- readme: contributors -start -->
<table>
    <tbody>
        <tr>
            <td align="center">
                <a href="https://github.com/Wilooper">
                    <img src="https://avatars.githubusercontent.com/u/198341775?v=4" width="100;" alt="Wilooper"/>
                    <br />
                    <sub><b>Shaurya singh (@Wilooper)</b></sub>
                </a>
            </td>
            <td align="center">
                <a href="https://github.com/thinkely">
                    <img src="https://avatars.githubusercontent.com/u/321372956?v=4" width="100;" alt="thinkely"/>
                    <br />
                    <sub><b>Shaurya singh (@thinkely)</b></sub>
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
    </tbody>
</table>
<!-- readme: contributors -end -->

---

## 📝 License

Licensed under the [MIT License](LICENSE) © 2026 Lyrica Contributors.
Made with ❤️ by [Shaurya Singh (Wilooper)](https://github.com/Wilooper) and the open-source community.
