# Environment Variables (`.env`)

Lyrica uses environment variables for sensitive tokens, infrastructure endpoints, and server configuration. Variables can be supplied in a local `.env` file or injected via Docker / cloud hosting environments.

---

## Environment Variable Reference

### 1. Security & Administrative Access

| Variable | Required | Default | Description |
|---|:---:|:---:|---|
| `ADMIN_KEY` | No | — | Secret token required to access administrative endpoints (`/cache/clear`, `/v2/proxy/*`, `/config/*`). |
| `LYRICA_ENV` | No | `development` | Set to `production` to enable strict security headers (CSP, HSTS), 60 RPM rate limits, and larger L1 memory caches. |
| `PORT` | No | `9999` (local) / `7860` (Docker) | Port on which the HTTP server listens. |
| `LOG_LEVEL` | No | `INFO` | Logging severity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `CORS_ORIGINS` | No | `*` | Comma-separated list of allowed CORS origins in production (e.g. `https://myfrontend.com`). |
| `TRUST_PROXY` | No | `0` | Number of trusted reverse-proxy hops. Set to `1` behind nginx/Traefik/Render so rate limiting sees the real client IP. |
| `MAX_CONTENT_LENGTH` | No | `1048576` | Maximum request body size in bytes (1 MiB). |
| `MAX_TEXT_LENGTH` | No | `200` | Maximum length for `artist`, `song`, and similar text query fields. |

---

### 2. Provider API Tokens

| Variable | Required | Default | Description |
|---|:---:|:---:|---|
| `GENIUS_TOKEN` | No | — | Genius client access token. If omitted, Lyrica uses the public unauthenticated search fallback. |
| `APPLE_MUSIC_DEVELOPER_TOKEN` | No | — | Apple Music Developer JWT token. Required for Apple Music source (ID 8) and syllable sync. |
| `APPLE_MUSIC_USER_TOKEN` | No | — | Optional Apple Music user subscription token. |
| `APPLE_STOREFRONT` | No | `us` | Default storefront country code for Apple Music. |
| `MUSIXMATCH_TOKEN` | No | — | Musixmatch client token. (Omit if using tokenless Lrcmux instead). |

---

### 3. Groq LLM (Translation & Romanization)

| Variable | Required | Default | Description |
|---|:---:|:---:|---|
| `GROQ_API_KEY` | No | — | Groq API key(s). Supports comma-separated keys for automatic round-robin load balancing (e.g. `gsk_key1,gsk_key2`). |
| `GROQ_MODEL` | No | `openai/gpt-oss-120b` | Groq model identifier used for translation and romanization. |

---

### 4. Cache & Rate Limiting Backend

| Variable | Required | Default | Description |
|---|:---:|:---:|---|
| `REDIS_URL` | No | — | Redis connection URL for L2 distributed cache (e.g. `redis://localhost:6379/0` or `redis://:pass@host:6379/0`). |
| `RATE_LIMIT_STORAGE_URI` | No | `memory://` | Storage backend for rate limiting. Defaults to `REDIS_URL` if set, otherwise in-memory. |
| `RATE_LIMIT_DEFAULT` | No | `60 per minute` (prod) / `15 per minute` (dev) | Default Flask-Limiter rule applied to every endpoint. |
| `CACHE_TTL` | No | `86400` (24h) | Cache expiration time in seconds (set to `604800` / 7 days in production Docker). |
| `CACHE_DIR` | No | `cache_data` | Directory where L3 disk JSON cache files are persisted. |
| `METADATA_CACHE_TTL` | No | `3600` | TTL in seconds for the in-process metadata cache. |
| `METADATA_CACHE_MAX` | No | `2000` | Maximum entries retained in the metadata cache. |
| `STATIC_CACHE_SECONDS` | No | `3600` | Browser cache lifetime for static assets. |

---

### 5. Proxy & Network Routing

| Variable | Required | Default | Description |
|---|:---:|:---:|---|
| `PROXY_URL` | No | — | Global proxy applied to ALL providers. Supports comma-separated list of HTTP/HTTPS/SOCKS5 proxies for round-robin pooling. |
| `YT_PROXY_URL` | No | — | Dedicated proxy applied exclusively to YouTube requests. |
| `YT_COOKIES_PATH` | No | — | Absolute filesystem path to `cookies.txt` for YouTube authentication. |
| `LRCLIB_API_URL` | No | `https://lrclib.net/api/get` | Override base URL for LRCLIB API. |
| `LRCMUX_API_URL` | No | `https://api.lrcmux.dev` | Override base URL for Lrcmux API. |
