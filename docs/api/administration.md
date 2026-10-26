# Administrative & System APIs

This guide details health monitoring, cache management, dynamic proxy pool administration, and runtime configuration reload endpoints.

---

## 1. Healthcheck (`GET /health`)

Probes service health. Used by Docker, Kubernetes, Render, and uptime monitors.

```http
GET /health
```

### Response

```json
{
  "status": "healthy",
  "version": "1.5.0",
  "service": "Lyrica",
  "mode": "production",
  "uptime_seconds": 120.4
}
```

`GET /health` performs no network I/O and is safe for aggressive liveness probes.

### Readiness (`GET /health/ready`)

Checks optional dependencies (currently Redis) and reports their state in the
body. Redis is an optional cache tier, so the endpoint still returns `200` when
it is unavailable.

```json
{
  "status": "ready",
  "version": "1.5.0",
  "service": "Lyrica",
  "redis": "connected"
}
```

---

## 2. Cache Management

### Public Cache Statistics (`GET /cache/stats`)
Returns high-level statistics about the multi-tier cache:

```http
GET /cache/stats
```

```json
{
  "status": "success",
  "backend": "memory+redis+disk",
  "memory_l1_items": 420,
  "redis_l2": {
    "connected": true,
    "keys": 128
  },
  "disk_l3_files": 128,
  "cache_files": 128,
  "ttl_seconds": 604800,
  "version": "v5"
}
```

`cache_dir` is intentionally omitted from this public response; it is only
included in the admin-authenticated `/admin/cache/stats` response.

### Invalidate Cache (`POST /cache/clear` or `POST /admin/cache/clear`)
Purges all cache tiers (L1 memory, L2 Redis keys, L3 disk files), plus the
in-process translation and metadata caches. Both routes are **POST-only**.

Requires `ADMIN_KEY` authentication via header or query string:

```bash
# Using Header
curl -X POST "http://127.0.0.1:9999/cache/clear" \
     -H "X-ADMIN-KEY: your_admin_key"

# Using Query Param
curl -X POST "http://127.0.0.1:9999/cache/clear?key=your_admin_key"
```

```json
{
  "status": "success",
  "data": {
    "cleared": true,
    "message": "All cache tiers successfully purged",
    "timestamp": "2026-10-26T03:45:00.000000+00:00"
  }
}
```

---

## 3. Proxy Pool Administration (`/v2/proxy/*`)

Lyrica includes a thread-safe round-robin proxy pool to prevent IP blocking on cloud providers.

### List Active Proxies (`GET /v2/proxy/list`)
Returns all active proxies in the pool (passwords and credentials are automatically masked):

```http
GET /v2/proxy/list
```

```json
{
  "status": "success",
  "data": {
    "total_proxies": 2,
    "proxies": [
      { "url": "http://user:***@proxy1.example.com:8080", "status": "active" },
      { "url": "socks5://proxy2.example.com:1080", "status": "active" }
    ]
  }
}
```

### Add Proxy to Pool (`POST /v2/proxy/set`)
Dynamically adds an HTTP, HTTPS, or SOCKS5 proxy to the pool without server restart:

```bash
curl -X POST "http://127.0.0.1:9999/v2/proxy/set" \
     -H "X-ADMIN-KEY: your_admin_key" \
     -H "Content-Type: application/json" \
     -d '{"proxy": "http://user:password@proxy.example.com:8080"}'
```

### Remove Proxy from Pool (`POST /v2/proxy/remove` or `DELETE`)

```bash
curl -X POST "http://127.0.0.1:9999/v2/proxy/remove" \
     -H "X-ADMIN-KEY: your_admin_key" \
     -H "Content-Type: application/json" \
     -d '{"proxy": "http://user:password@proxy.example.com:8080"}'
```

### Clear All Proxies (`POST /v2/proxy/clear`)

```bash
curl -X POST "http://127.0.0.1:9999/v2/proxy/clear" \
     -H "X-ADMIN-KEY: your_admin_key"
```

---

## 4. Configuration Management (`/config/*`)

Lyrica supports runtime preference modification via `.lyrica.config`.

### Check Configuration Status (`GET /config/status`)

```http
GET /config/status
```

```json
{
  "status": "success",
  "data": {
    "config_path": ".lyrica.config",
    "defaults": {
      "default_source": "lrclib",
      "fast_mode": false,
      "timestamps": false
    }
  }
}
```

### Hot-Reload Configuration (`POST /config/reload`)
Re-reads `.lyrica.config` from disk without restarting the application:

```bash
curl -X POST "http://127.0.0.1:9999/config/reload" \
     -H "X-ADMIN-KEY: your_admin_key"
```

---

## 5. Web Interface (`GET /app`)

Lyrica includes a built-in interactive web UI at `/app` for visual lyrics lookup, playback, translation testing, and karaoke demonstrations.
