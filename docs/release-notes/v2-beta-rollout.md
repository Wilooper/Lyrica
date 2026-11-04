# Lyrica v2-beta-rollout

**Release:** `v2-beta-rollout`  
**Package version:** `2.0.0b1`  
**Status:** Beta / pre-release  
**Date:** 2026-11-04

Lyrica `v2-beta-rollout` is an additive beta release. The existing v1 endpoint
at `/lyrics/` remains available and unchanged. The new v2 API lives under
`/v2/` and is intentionally leaner, stricter about sync tiers, and easier to
cache.

> This is a beta. The v2 response contract and provider routing may change
> before a stable v2 release. Use v1 if you need the previous contract
> unchanged.

---

## Highlights

### v1 stays put, v2 is additive

| Version | Endpoint | Status |
|---|---|---|
| v1 | `GET /lyrics/` | Unchanged, still supported |
| v2 | `GET /v2/lyrics` | New lean beta endpoint |
| v2 | `GET /v2/capabilities` | New provider/sync capability discovery |
| v2 | `GET /v2/health` | New provider health and metrics summary |

Both versions are served by the same deployment. There is no separate v1 host,
port, or `/v1/lyrics` alias.

### Lean v2 responses

`/v2/lyrics` returns compact `[start_ms, text]` lines, uses small error
envelopes, supports `ETag` / `304 Not Modified`, and exposes explicit sync
tiers (`line`, `word`, `syllable`). Clients can request a lower tier
explicitly, or require an exact tier with `allow_lower=false`.

### Reliability and caching

- Response verification before results are cached.
- Canonical raw-cache records plus derived tier views, so a richer result is
  not overwritten by a lower-tier result.
- Single-flight request coalescing for identical in-flight work.
- Negative caching for misses.
- Per-provider token buckets, circuit breakers, bulkheads, and live metrics.
- `CACHE_VERSION` bumped to **`v6`** because the stored record shape changed.
  Older cache entries are ignored and rebuilt.

### Provider behavior

- **YouTube Music is disabled** until its fetcher is rebuilt.
- **Musixmatch** is loaded only when `MUSIXMATCH_TOKEN` is present.
- **Apple Music** is loaded only when `APPLE_MUSIC_DEVELOPER_TOKEN` or
  `DEVELOPER_TOKEN` is present.
- Automatic word/syllable routing is restricted to **`lrcmux`** and
  **`apple_music`**. Explicit `pass=true` provider sequences remain
  authoritative.
- A redundant line-phase lookup was removed for restricted word-only chains.
  This reduces duplicate provider work when a word request has to fall back.

### Zero-config baseline

The default install still works without Redis, an AI key, or any provider
token. Redis, Groq translation/romanization, Apple Music, and Musixmatch are
optional enhancements.

Compression is opt-in only:

```bash
LYRICA_COMPRESS=true
```

---

## Compatibility and upgrade notes

- Existing v1 clients can continue calling `/lyrics/` without changes.
- New clients should use `/v2/lyrics`.
- Old cache entries are not reused because `CACHE_VERSION` is now `v6`.
- Python `>=3.11` is required.
- Docker image tag for this release: `v2-beta-rollout`.
- Roll back by deploying the previous tag and continuing to use `/lyrics/`.

### Quick v2 examples

```bash
# Line-level lyrics
curl -s "http://127.0.0.1:9999/v2/lyrics?artist=Coldplay&song=Yellow&tier=line"

# Word-level request, allowing a lower tier if word sync is unavailable
curl -s "http://127.0.0.1:9999/v2/lyrics?artist=Coldplay&song=Yellow&tier=word"

# Require word sync exactly; returns 404 tier_unavailable if unavailable
curl -s "http://127.0.0.1:9999/v2/lyrics?artist=Coldplay&song=Yellow&tier=word&allow_lower=false"

# Discover provider and tier support
curl -s "http://127.0.0.1:9999/v2/capabilities"
```

---

## Verification results

All results below were collected on the release preparation host:

| Item | Value |
|---|---|
| Host | WSL2 Linux 6.18, x86_64 |
| CPU | 13th Gen Intel Core i5-13420H (6 cores / 12 threads) |
| Python | 3.13.12 |
| Flask | 3.1.3 |
| Server for HTTP tests | Flask development server, logging enabled |
| Rate limiting during HTTP benchmark | Disabled (`RATELIMIT_ENABLED=false`) |

### Automated tests

| Check | Command | Result |
|---|---|---|
| Acceptance / regression suite | `python3 -m pytest Test -q` | **46 passed, 4 skipped** in 30.82s |
| Documentation links | `python3 scripts/verify_docs.py` | **Passed** |
| Python bytecode compile | `python3 -m compileall -q src` | **Passed** |
| Performance harness | `python3 Test/test_performance.py` | Completed |

The 4 skipped tests are environment/credential-dependent and do not indicate
failures.

### In-process performance matrix

Measured with `Test/test_performance.py`:

| Component | Requests | Concurrency | Throughput | p50 | p95 | p99 |
|---|---:|---:|---:|---:|---:|---:|
| L1 in-memory cache | 10,000 | 50 | **68,624.1 req/s** | 0.0003 ms | 0.0015 ms | 0.0034 ms |
| Flask test client | 1,000 | 25 | **3,266.4 req/s** | 0.244 ms | 0.814 ms | 114.255 ms |
| L1 cache hit latency | 1 | 1 | — | **0.0148 ms** | — | — |

The Flask test client p99 includes occasional scheduler/GC outliers. The L1
cache numbers are a microbenchmark, not an end-to-end HTTP guarantee.

### Live HTTP performance matrix

Local Flask development server, 500 requests per endpoint, concurrency 20:

| Endpoint | Throughput | p50 | p95 | p99 |
|---|---:|---:|---:|---:|
| `GET /v2/lyrics` cached line | **675.2 req/s** | 28.614 ms | 38.718 ms | 44.285 ms |
| `GET /lyrics/` cached timed (v1) | **588.6 req/s** | 33.544 ms | 39.670 ms | 43.180 ms |
| `GET /v2/capabilities` | **792.0 req/s** | 23.451 ms | 38.200 ms | 42.990 ms |
| `GET /v2/health` | **600.1 req/s** | 32.651 ms | 39.051 ms | 42.740 ms |

These numbers come from Flask's development server, not a production Gunicorn
deployment. They are useful for regression comparison, not as a production
capacity promise. A production deployment should be benchmarked behind its
actual WSGI server, worker count, reverse proxy, and cache backend.

### Live provider smoke matrix

Observed against live providers on the release host. Latency is
network-dependent and varies by provider, region, and time of day.

| Request | Status | Observed latency | Tier / source | Lines |
|---|---:|---:|---|---:|
| v2 line — Fleetwood Mac, “Dreams” | 200 | 12,127 ms | line / lrclib | 34 |
| v2 line — Arijit Singh, “Tum Hi Ho” | 200 | 4,093 ms | line / lrclib | 45 |
| v2 line — Bad Bunny, “Tití Me Preguntó” | 200 | 52,373 ms | line / netease | 75 |
| v2 line — NewJeans, “Ditto” | 200 | 8,487 ms | line / lrclib | 44 |
| v2 line — Queen, “Bohemian Rhapsody” | 200 | 8,582 ms | line / lrclib | 50 |
| v2 word — Fleetwood Mac, “Dreams” | 200 | 16,734 ms | line fallback / lrclib | 34 |
| v2 word — Arijit Singh, “Tum Hi Ho” | 200 | 29,617 ms | line fallback / lrclib | 45 |
| v1 timed — NewJeans, “Ditto” | 200 | 13 ms (cached) | lrclib | 44 timed |
| v2 strict word — NewJeans, “Ditto” | 404 | 16,321 ms | `tier_unavailable` | 0 |

Notes:

- The 52.4s NetEase result is a provider outlier, not a target latency.
- Word requests fell back to line-level lyrics because `lrcmux` did not return
  usable word timing for those songs.
- The strict word request returned `404 tier_unavailable` as designed.
- Cached v1 responses remain fast; the 13ms result was served from cache.

---

## Security and transparency

This release was prepared with a secret audit before packaging:

| Check | Result |
|---|---|
| Tracked `.env`, cookie, auth, token, key, or credential files | **None found** |
| Common token/private-key pattern scan in the working tree | **No matches** |
| Sensitive filenames in git history | **None found** |
| `.env` / credentials included in the release commit | **No** |
| Runtime caches included in the release commit | **No** |
| User AI keys, cookies, or auth headers logged/cached | **No** |

`.gitignore` covers `.env`, `*.env`, `.lyrica.config`, cookie/auth files,
`cache_data/`, `site/`, virtual environments, and related runtime artifacts.
The example environment file contains placeholders only.

No API key, password, cookie, token, or private key is required to run the
zero-config baseline. If you enable optional providers or AI features, keep
those credentials in your own environment and never commit them.

---

## Known limitations

- This is a **beta** release; v2 behavior may change before stable v2.
- `lrcmux` can return line/plain lyrics even when word sync is requested.
  Automatic word requests therefore fall back to line level, and strict word
  requests return `404 tier_unavailable`.
- Apple Music and Musixmatch require their own tokens and are not part of the
  zero-config source set.
- YouTube Music remains disabled until its fetcher is rebuilt.
- Live provider latency varies widely. Some sources are slow, rate-limited, or
  unavailable from some networks.
- The HTTP benchmark above uses the Flask development server, not production
  Gunicorn. Do not treat it as a production SLA.
- Translation and romanization require an optional Groq API key.

---

## Documentation

- [v2 API contract](../api/v2.md)
- [v1 lyrics API](../api/lyrics.md)
- [Fallback and tier routing](../architecture/fallback.md)
- [Caching architecture](../architecture/caching.md)
- [Provider availability matrix](../providers/overview.md)
- [Environment variables](../configuration/environment.md)
- [Docker deployment](../deployment/docker.md)
- [Testing and benchmarking](../development/testing.md)

---

## Release checklist

- [x] v1 `/lyrics/` unchanged
- [x] v2 endpoints added under `/v2/`
- [x] YouTube Music disabled
- [x] Musixmatch and Apple Music token-gated
- [x] Word/syllable routing restricted to `lrcmux` + `apple_music`
- [x] Cache version bumped to `v6`
- [x] Tests passing (`46 passed, 4 skipped`)
- [x] Documentation link audit passing
- [x] Runtime caches cleared
- [x] Secret audit completed
- [x] Release notes prepared
