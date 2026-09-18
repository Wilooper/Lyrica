# 🌐 Lyrica — Lyrics Translation & Romanization Guide

Lyrica includes built-in real-time lyrics translation and romanization (transliteration) powered by **Groq LLM** (`openai/gpt-oss-120b`). 

This feature operates seamlessly on both **synced timestamped LRC lyrics** and **unsynced plain text lyrics**, making foreign language tracks accessible to global listeners.

---

## ⚡ How It Works

When you attach `&translate=true` and/or `&romanize=true` to your `/lyrics/` requests, Lyrica automatically:

1. **Fetches Lyrics**: Retrieves lyrics from the preferred active fetcher (e.g. LRCLIB, Genius, YouTube Music, Lrcmux).
2. **Line Sanitization**: Isolates non-empty lines while preserving exact original line indices and structural line breaks.
3. **Groq Round-Robin Processing**: Routes the text to Groq API using a thread-safe multi-key pool with automated failover.
4. **Line-Count Validation**: Strictly validates that the LLM response preserves line alignment.
5. **Structure Reconstruction**: Re-inserts line breaks and maps translations/romanizations directly back onto each line (or individual `timed_lyrics` item).
6. **Subdirectory Caching**: Stores results in `cache_data/translations/` to maximize performance and avoid unnecessary LLM API costs.

---

## 🔑 Environment Setup (`.env`)

Add your Groq API key(s) to `.env`:

```env
# ── Groq LLM Key Configuration ────────────────────────────────
# Single Key:
GROQ_API_KEY=gsk_your_groq_api_key_here

# Multiple Keys (Comma-Separated for Load Balancing & Failover):
GROQ_API_KEY=gsk_key1,gsk_key2,gsk_key3

# Custom Groq Model (Optional, default: openai/gpt-oss-120b)
# Note: Groq may deprecate or remove support for specific models at any time.
# If openai/gpt-oss-120b becomes unavailable, set GROQ_MODEL to any other
# available Groq model of your preference from https://console.groq.com/docs/models
GROQ_MODEL=openai/gpt-oss-120b
```

### 🛡️ Smart Multi-Key Pool & Cooldowns

Lyrica includes a thread-safe `GroqKeyManager` singleton that provides:
- **Round-Robin Load Distribution**: Evenly balances LLM requests across all configured keys.
- **24-Hour Quarantining (401/403)**: Automatically disables revoked or invalid keys for 24 hours.
- **60-Second Cooldown (429 Rate Limits)**: Temporarily suspends rate-limited keys for 60 seconds before retrying them.
- **Key Masking**: Hashes and masks Groq API keys in logs for security.

---

## ⚙️ User Preferences (`.lyrica.config`)

Default application settings can be configured under `[defaults]` in `.lyrica.config`:

```ini
[defaults]
translate = false       # Enable translation by default
romanize  = false       # Enable romanization by default
language  = en          # Target language (e.g., en, spanish, hindi, japanese, french)
```

---

## 📚 API Usage Examples

### 1. Synced Lyrics Translation & Romanization

```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Karan%20Aujla&song=Boyfriend&timestamps=true&translate=true&romanize=true&language=en"
```

**JSON Response Schema:**

```json
{
  "status": "success",
  "data": {
    "artist": "Karan Aujla",
    "title": "Boyfriend",
    "source": "lrclib",
    "hasTimestamps": true,
    "translation_metadata": {
      "target_language": "en",
      "processed_by": "groq/openai/gpt-oss-120b",
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
      }
    ]
  }
}
```

### 2. Unsynced Lyrics Translation & Romanization

```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Arijit%20Singh&song=Tum%20Hi%20Ho&translate=true&romanize=true&language=en"
```

**JSON Response Schema:**

```json
{
  "status": "success",
  "data": {
    "artist": "Arijit Singh",
    "title": "Tum Hi Ho",
    "source": "genius",
    "hasTimestamps": false,
    "lyrics": "Hum tere bin ab reh nahi sakte\nTere bina kya wajood mera",
    "translated_lyrics": "I cannot live without you now\nWithout you, what existence do I have?",
    "romanized_lyrics": "Hum tere bin ab reh nahi sakte\nTere bina kya wajood mera",
    "translation_metadata": {
      "target_language": "en",
      "processed_by": "groq/openai/gpt-oss-120b",
      "cached_from": "fresh"
    }
  }
}
```

---

## 🎯 Target Language Options

The `language` parameter accepts common language names and standard codes:
- English: `en` or `english`
- Hindi: `hi` or `hindi`
- Spanish: `es` or `spanish`
- French: `fr` or `french`
- German: `de` or `german`
- Japanese: `ja` or `japanese`
- Korean: `ko` or `korean`

---

## ⚠️ Error Handling & Resilience

1. **`503 Service Unavailable`**: Returned if `translate=true` or `romanize=true` is requested but no `GROQ_API_KEY` is defined or all keys are in cooldown.
2. **Line Count Validation & Fail-safe**: If the LLM returns an unexpected line count, Lyrica retries up to 2 times with alternate keys. If all retries fail, it gracefully returns original lyrics with a `translation_error` notice rather than failing the request.
3. **Separate Caching**: Translation results are cached in `cache_data/translations/` independently of the main lyrics cache.
