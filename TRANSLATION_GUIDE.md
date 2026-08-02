# Lyrica Translation & Transliteration Guide

Lyrica supports real-time, high-fidelity lyrics translation and romanization (transliteration) powered by Groq LLM (`llama-3.3-70b-versatile`). 

This feature operates seamlessly on both **synced (timestamped LRC)** and **unsynced (plain)** lyrics formats.

---

## 🚀 How It Works

By attaching `&translate=true` and/or `&romanize=true` to your `/lyrics/` requests, Lyrica automatically:
1. Retrieves the song lyrics from the selected source (such as LRCLIB or Genius).
2. Sanitizes and isolates text lines (excluding blank lines to avoid model confusion).
3. Connects to Groq using a rotatable, round-robin key pool.
4. Performs translation/transliteration.
5. Reconstructs original lyrics structure (re-inserting blank lines at correct offsets).
6. Caches results inside a separate `cache_data/translations/` file-based system to maximize performance and minimize LLM costs.

---

## 🔑 Environment Setup (`.env`)

Add your Groq API key(s) to your `.env` file. You can pass a single key or a comma-separated list of multiple keys for round-robin load distribution and automatic failover:

```ini
# ── Groq AI (Translation & Transliteration) ─────────────────────
# Single Key Example:
GROQ_API_KEY=gsk_your_key_here

# Multiple Keys Example (Load-Balanced):
# GROQ_API_KEY=gsk_key1,gsk_key2,gsk_key3
```

### 🛡️ Smart Key Management & Cooldowns
Lyrica includes an advanced, thread-safe `GroqKeyManager` that handles keys gracefully:
- **Round-Robin Load Distribution**: Distributes queries sequentially among all healthy keys.
- **24-Hour Cooldown**: If any key fails with an authentication error (e.g. `401 Unauthorized` or `403 Forbidden` due to expired or revoked keys), it is quarantined and skipped for 24 hours.
- **60-Second Cooldown**: If a key hits rate limits (`429 Too Many Requests`), it is quarantined for 60 seconds.

---

## ⚙️ User Configuration (`.lyrica.config`)

You can set application-wide defaults for the translation feature under the `[defaults]` section of your `.lyrica.config` file:

```ini
[defaults]
translate = false       ; Set to true to translate lyrics by default
romanize  = false       ; Set to true to romanize/transliterate lyrics by default
language  = en          ; Default target language/script (e.g. en, hindi, spanish, japanese)
```

---

## 📚 API Endpoint Usage

### 1. Synced Lyrics Translation & Romanization
**Request:**
```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Karan%20Aujla&song=Boyfriend&timestamps=true&translate=true&romanize=true&language=en"
```

**Response Format:**
```json
{
  "status": "success",
  "data": {
    "album": "Making Memories",
    "artist": "Karan Aujla",
    "title": "Boyfriend",
    "duration": 161.0,
    "hasTimestamps": true,
    "instrumental": false,
    "source": "lrclib",
    "timestamp": "2026-08-02 16:13:37",
    "translation_metadata": {
      "target_language": "en",
      "processed_by": "groq/llama-3.3-70b-versatile",
      "cached_from": "fresh"
    },
    "timed_lyrics": [
      {
        "id": "lrc_0",
        "start_time": 10550,
        "end_time": 13260,
        "text": "Tai Nu Keh, Rakh Hun Bidka’an Na",
        "romanized": "Tai Nu Keh, Rakh Hun Bidka'an Na",
        "translated": "Tell him to stop spying on me now"
      },
      ...
    ]
  }
}
```

### 2. Unsynced Lyrics Translation & Romanization
**Request:**
```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Karan%20Aujla&song=Boyfriend&translate=true&romanize=true&language=en"
```

**Response Format:**
```json
{
  "status": "success",
  "data": {
    "album": "Making Memories",
    "artist": "Karan Aujla",
    "title": "Boyfriend",
    "duration": 161.0,
    "hasTimestamps": false,
    "instrumental": false,
    "source": "lrclib",
    "timestamp": "2026-08-02 16:13:37",
    "lyrics": "Tai Nu Keh, Rakh Hun Bidka’an Na\nTu Vi Mainu Maari’n Maaye Jhidka’an Na",
    "translated_lyrics": "Tell him to stop spying on me now\nAnd mother, you shouldn't scold me either",
    "romanized_lyrics": "Tai Nu Keh, Rakh Hun Bidka'an Na\nTu Vi Mainu Maari'n Maaye Jhidka'an Na",
    "translation_metadata": {
      "target_language": "en",
      "processed_by": "groq/llama-3.3-70b-versatile",
      "cached_from": "fresh"
    }
  }
}
```

> [!TIP]
> If you only request `translate=true` or `romanize=true` individually, the other field (e.g. `romanized` / `romanized_lyrics`) will be omitted from the JSON response.

---

## ⚡ Error Codes & Failures

- **`503 Service Unavailable`**: Returned if the translate/romanize features are requested, but no `GROQ_API_KEY` env var is configured, or all configured keys are in cooldown.
- **Fail-safe Line Count Validation**: The translation pipeline verifies that the LLM returned exactly the same number of lines as sent. In the rare event of a line-count mismatch:
  1. Lyrica will automatically retry with a different key (up to 2 times).
  2. If all retries fail line-count validation, it gracefully returns the original lyrics with a `translation_error` message inside the response rather than crashing the request.
