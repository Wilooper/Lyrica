# Troubleshooting & FAQ

This guide addresses common questions, error codes, and troubleshooting steps.

---

## Frequently Asked Questions

### 1. Why are some Genius lyrics missing verses?
**Resolved in v1.5.0**: Older versions of the Genius fetcher used a non-greedy regex (`(.*?)</div>`) that halted prematurely on inner annotation tags. In v1.5.0, a tag-depth tracking parser (`_extract_container_contents`) was introduced that tracks nested opening and closing div depths to reliably extract complete verses, choruses, and outros without truncation.

### 2. Why am I receiving `403 Forbidden` on `/cache/clear` or admin endpoints?
Administrative routes require the `ADMIN_KEY` configured in `.env`. Ensure you pass it via the `X-ADMIN-KEY` header or `?key=` query parameter. If `ADMIN_KEY` is not set in `.env`, all administrative actions are locked for security.

### 3. YouTube Music returns empty results or errors on cloud servers.
Major cloud platforms (AWS, DigitalOcean, Hetzner, Render) have datacenter IP ranges that YouTube blocks by default.
- **Solution 1**: Set `YT_PROXY_URL` in `.env` to route YouTube queries through a residential proxy.
- **Solution 2**: Supply a YouTube cookies export via `YT_COOKIES_PATH=/path/to/cookies.txt`.
- **Solution 3**: Fall back to LRCLIB or Lrcmux by adjusting `sequence=lrclib,lrcmux`.

### 4. Why is Apple Music returning `None` or skipped?
Apple Music requires an Apple Music Developer JWT token. If `APPLE_MUSIC_DEVELOPER_TOKEN` is not set in `.env`, Lyrica automatically skips Apple Music during startup without error and degrades gracefully to Lrcmux or LRCLIB.

### 5. How do I prevent Groq LLM rate limits during lyrics translation?
Groq enforces strict per-minute token and request limits. To avoid 429 errors:
1. Provide **multiple Groq API keys** in `GROQ_API_KEY`, separated by commas:
   ```ini
   GROQ_API_KEY=gsk_key1,gsk_key2,gsk_key3
   ```
   Lyrica's `GroqKeyManager` automatically round-robins across all keys and enforces cooldown periods on individual keys if they encounter a 429.
2. Translation outputs are cached in the translation cache tier, so identical requests never hit the Groq API twice.

### 6. How do I change the server port?
- **Local Dev Server**: Set `PORT=XXXX` in `.env` or run `PORT=8000 python run.py`.
- **Docker Compose**: Set `PORT=8080` in `.env` or edit the ports mapping in `docker-compose.yml`.
- **Gunicorn**: Pass `-b 0.0.0.0:XXXX` to Gunicorn.

---

## Diagnostic Checklist

If you encounter unexpected behavior:

1. **Check Server Health**:
   ```bash
   curl -s http://127.0.0.1:9999/health
   ```
2. **Inspect Cache Status**:
   ```bash
   curl -s http://127.0.0.1:9999/cache/stats
   ```
3. **Run Verification Test Suite**:
   ```bash
   python Test/run_all_tests.py
   ```
4. **Enable Debug Logging**:
   Set `LOG_LEVEL=DEBUG` in `.env` to see detailed network traces and provider matching logs in the terminal.
