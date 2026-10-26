# Quickstart Guide

This guide gets you up and running with Lyrica in under 5 minutes.

---

## 1. Start the Server

Ensure you have cloned the repository and installed dependencies (see [Installation](installation.md) if you haven't yet).

```bash
# Start local multi-threaded development server
python run.py
```

The server initializes on `http://127.0.0.1:9999`.

---

## 2. Check API Health

Verify the server is running:

```bash
curl -s http://127.0.0.1:9999/health
```

Expected response:

```json
{
  "status": "healthy",
  "version": "1.5.0",
  "service": "Lyrica"
}
```

---

## 3. Basic Plain Lyrics

Fetch plain text lyrics for any song:

```bash
curl -s "http://127.0.0.1:9999/lyrics/?artist=Coldplay&song=Yellow"
```

Response:

```json
{
  "status": "success",
  "data": {
    "source": "lrclib",
    "artist": "Coldplay",
    "title": "Yellow",
    "lyrics": "Look at the stars\nLook how they shine for you\nAnd everything you do...",
    "hasTimestamps": false
  }
}
```

---

## 4. Synchronized Timestamps (LRC)

Add `&timestamps=true` to receive millisecond-accurate timing:

```bash
curl -s "http://127.0.0.1:9999/lyrics/?artist=Coldplay&song=Yellow&timestamps=true"
```

```json
{
  "status": "success",
  "data": {
    "source": "lrclib",
    "artist": "Coldplay",
    "title": "Yellow",
    "hasTimestamps": true,
    "sync_level": "line",
    "timed_lyrics": [
      {
        "id": "lrc_0",
        "text": "Look at the stars",
        "start_time": 36189,
        "end_time": 37719
      }
    ]
  }
}
```

---

## 5. Word-Level Sync (Karaoke Mode)

Add `&word=true` (requires `&timestamps=true`):

```bash
curl -s "http://127.0.0.1:9999/lyrics/?artist=Coldplay&song=Yellow&timestamps=true&word=true"
```

Each line will include a `words` array with individual start/end millisecond offsets.

---

## 6. Fast Parallel Mode with Mood & Metadata

Query multiple providers concurrently and enrich the response with mood analysis and album cover art:

```bash
curl -s "http://127.0.0.1:9999/lyrics/?artist=Queen&song=Bohemian%20Rhapsody&fast=true&mood=true&metadata=true"
```

The response includes:
- `lyrics`: Aggregated lyrics
- `sentiment`: Sentiment classification, polarity score, subjectivity score, and top word frequencies
- `metadata`: Album name, cover art URL, duration, release date, and genre

---

## Next Steps

- Explore all parameters in the [Lyrics API Reference](../api/lyrics.md)
- Learn about [AI Translation & Romanization](../api/lyrics.md#ai-translation-romanization)
- Review [Production Deployment](../deployment/docker.md)
