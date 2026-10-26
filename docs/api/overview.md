# API Overview & Conventions

This document details the architectural conventions, base URLs, authentication schemes, rate limits, and standard response envelopes used by all Lyrica endpoints.

---

## Base URLs

| Environment | Base URL | Notes |
|---|---|---|
| **Local Development** | `http://127.0.0.1:9999` | Default port used by `python run.py` |
| **Docker / Container** | `http://localhost:7860` | Default port used by `Dockerfile` and `docker-compose.yml` |
| **Production Cloud** | Configured via `PORT` env var | Defaults to `PORT=7860` or platform default |

---

## Authentication

### Public Endpoints
All consumer-facing endpoints do **not** require authentication:
- `GET /lyrics/`
- `GET /metadata/`
- `GET /trending/`
- `GET /suggestion`
- `GET /analytics/*`
- `GET /api/jiosaavn/*`
- `GET /health`
- `GET /health/ready`
- `GET /cache/stats`

### Administrative Endpoints
Administrative endpoints (`/cache/clear`, `/admin/*`, `/v2/proxy/*`, `/config/*`) require the `ADMIN_KEY` configured in `.env`.

You can supply the admin key in two ways:

1. **Header (Recommended)**:
   ```http
   X-ADMIN-KEY: your_admin_key_here
   ```

2. **Query Parameter**:
   ```http
   POST /cache/clear?key=your_admin_key_here
   ```

If `ADMIN_KEY` is not configured or matches incorrectly, the server returns `403 Forbidden`.

---

## Standard Response Envelopes

Every JSON response from Lyrica follows a predictable structure.

### Success Envelope

HTTP Status: `200 OK`

```json
{
  "status": "success",
  "data": {
    "source": "lrclib",
    "artist": "Coldplay",
    "title": "Yellow",
    "hasTimestamps": false,
    "lyrics": "Look at the stars..."
  }
}
```

### Error Envelope

HTTP Status: `400 Bad Request`, `403 Forbidden`, `404 Not Found`, `405 Method Not Allowed`, `413 Payload Too Large`, `429 Too Many Requests`, `500 Internal Server Error`, `502 Bad Gateway`, or `504 Gateway Timeout`

```json
{
  "status": "error",
  "error": {
    "message": "Missing required parameters: artist and song are required",
    "timestamp": "2026-10-26T03:45:00.000000+00:00"
  }
}
```

---

## HTTP Status Codes

| Code | Meaning | When it Occurs |
|:---:|---|---|
| `200` | OK | Request was successful and results were returned |
| `400` | Bad Request | Missing/invalid parameters, or a text field exceeds the configured limit |
| `403` | Forbidden | Admin key missing or invalid on protected endpoints |
| `404` | Not Found | Route does not exist, or lyrics were not found across all fallbacks |
| `405` | Method Not Allowed | Wrong HTTP method (for example `GET /admin/cache/clear`) |
| `413` | Payload Too Large | Request body exceeds `MAX_CONTENT_LENGTH` |
| `429` | Too Many Requests | Rate limit exceeded |
| `500` | Internal Server Error | Unhandled server error (logs are written to server stderr) |
| `502` | Bad Gateway | An upstream provider (for example MusicBrainz) failed |
| `504` | Gateway Timeout | An upstream provider or async operation timed out |

---

## Rate Limiting

Lyrica uses Flask-Limiter for request throttling:
- **Development Mode**: `15 requests per minute` per IP address.
- **Production Mode (`LYRICA_ENV=production`)**: `60 requests per minute` per IP address (customizable via `RATE_LIMIT_DEFAULT`).
- **Storage Backend**: Defaults to in-memory (`memory://`) or distributed Redis (`REDIS_URL` or `RATE_LIMIT_STORAGE_URI`).

Rate limit headers are automatically attached to responses:
```http
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 59
X-RateLimit-Reset: 1730000000
```
