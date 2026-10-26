# Architecture Overview

This document provides a technical deep dive into Lyrica's system design, concurrency model, and request lifecycles.

---

## High-Level System Architecture

```mermaid
graph TD
    Client([HTTP Client / SDK / Frontend])

    subgraph Server["Lyrica Application Layer (Flask + Gevent / Gthread)"]
        Router["REST Router (src/router.py)"]
        AsyncBridge["Async-Sync Bridge (run_async)"]
        Limiter["Rate Limiter (Flask-Limiter)"]
        Security["Security Headers & CORS"]
        ProxyMgr["Proxy Pool Manager (src/proxy_manager.py)"]
        UserCfg["User Config (.lyrica.config)"]
    end

    subgraph Caching["Multi-Tier Caching System (src/cache.py)"]
        L1["L1: In-Memory LRU Cache (Capacity: 5000 in prod)"]
        L2["L2: Redis Distributed Cache (REDIS_URL)"]
        L3["L3: Persistent Disk JSON Cache (cache_data/)"]
    end

    subgraph Controller["Fetch & Processing Engine"]
        FetchCtrl["Fetch Controller (src/fetch_controller.py)"]
        Pool["HTTPX Async Connection Pool (max_connections=200)"]
        GroqMgr["Groq Key Manager & Processor (src/groq_processor.py)"]
        Sentiment["Sentiment & Word Analyzer (src/sentiment_analyzer.py)"]
        MetadataEng["Async Metadata Aggregator (src/metadata_extractor.py)"]
    end

    subgraph Providers["Lyrics Providers (8 Sources)"]
        P1["LRCLIB"]
        P2["Lrcmux (Musixmatch)"]
        P3["Genius (Depth-tracking)"]
        P4["Apple Music (Syllable & Word)"]
        P5["YouTube Music"]
        P6["NetEase"]
        P7["Megalobiz"]
        P8["Musixmatch"]
    end

    Client --> Router
    Router --> Security
    Router --> Limiter
    Router --> AsyncBridge
    AsyncBridge --> Caching
    Caching -- Hit --> Router
    Caching -- Miss --> FetchCtrl

    FetchCtrl --> Pool
    Pool --> Providers
    FetchCtrl --> GroqMgr
    FetchCtrl --> Sentiment
    FetchCtrl --> MetadataEng
    FetchCtrl --> Caching
```

---

## Request Lifecycle Sequence

The following sequence illustrates what happens when a client requests synchronized, translated lyrics:

```mermaid
sequenceDiagram
    autonumber
    actor Client
    participant Router as REST Router
    participant Cache as Multi-Tier Cache
    participant Controller as Fetch Controller
    participant Provider as Lyrics Sources
    participant Groq as Groq LLM API

    Client->>Router: GET /lyrics/?artist=...&song=...&timestamps=true&translate=true
    Router->>Cache: Lookup SHA-256 Key (v5)
    alt Cache Hit (L1 / L2 / L3)
        Cache-->>Router: Return Cached Envelope (0.003ms)
        Router-->>Client: 200 OK (Instant Response)
    else Cache Miss
        Router->>Controller: Initiate Fetch (timestamps=True)
        Controller->>Provider: Query Sources according to Fallback / Fast mode
        Provider-->>Controller: Return Synchronized Lyrics
        opt Translation Requested (translate=True)
            Controller->>Groq: Request Neural Translation via Groq API
            Groq-->>Controller: Return Translated Lyrics
        end
        Controller->>Cache: Save Envelope into L1 Memory, L2 Redis, and L3 Disk
        Controller-->>Router: Assembled Result
        Router-->>Client: 200 OK JSON Response
    end
```

---

## Core Components

### 1. Flask App Factory (`src/app.py`)
- Initializes Flask with CORS, gzip compression via `Flask-Compress`, and Flask-Limiter.
- Detects `LYRICA_ENV=production`:
    - Enforces HSTS, CSP, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`.
    - Adjusts default rate limits (e.g. 60 RPM).
    - Seeds the proxy pool from `PROXY_URL`.

### 2. Async-to-Sync Bridge (`run_async()` in `src/router.py`)
Flask routes run synchronously in worker threads, while provider integrations and metadata extractors use `httpx.AsyncClient` with `asyncio.gather` for non-blocking I/O. The `run_async()` bridge manages event loops cleanly with `nest_asyncio` and timeouts.

### 3. Shared HTTP Connection Pool (`src/sources/base_fetcher.py`)
All fetchers inherit from `BaseFetcher` and utilize a centralized, thread-safe `httpx.AsyncClient` with connection pooling (`max_connections=200`, `max_keepalive_connections=50`). This prevents socket exhaustion during high concurrent request bursts.

### 4. Fetch Controller (`src/fetch_controller.py`)
Orchestrates provider execution order, handles the intelligent multi-sync degradation hierarchy (syllable → word → line → plain), and supports both sequential fallback and parallel (`fast=true`) modes.
