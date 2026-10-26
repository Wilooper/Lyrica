# 🎤 Lyrica — Word-Level Sync (Karaoke) Guide

Word-level synchronization provides millimeter-precise timestamps (in milliseconds) for **every individual word** in a song's lyrics line. Unlike line-level sync (which tells you when a whole sentence starts), word-level sync allows software to track and highlight words dynamically as they are sung.

Use word-level sync to power:
- 🎤 **Karaoke Applications** — highlight exact words in real-time
- 🎬 **Animated Lyric Displays** — reveal or scale words as they play
- ♿ **Accessibility Tools** — word-by-word read-along synchronization
- 🗣️ **Language Learning Apps** — track pronunciation speed and exact timing

---

## ⚡ How to Request Word-Level Sync

Add `&word=true` and `&timestamps=true` to any `/lyrics/` API request:

```bash
GET /lyrics/?artist=Coldplay&song=Yellow&timestamps=true&word=true
```

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `timestamps` | boolean | Yes | `false` | Must be `true` to receive synchronized timed lyrics |
| `word` | boolean | Yes | `false` | Requests per-word timestamps via Lrcmux |
| `sequence` | string | No | `2,7,1,3,4,5,6` | Source preference list. Use `sequence=7` or `sequence=lrcmux` to force Lrcmux |
| `pass` | boolean | No | `false` | When `true`, restricts search strictly to sources in `sequence` |

> [!NOTE]
> Word-level sync data is provided by **Lrcmux (Source ID 7)** and **Apple Music (Source ID 8)**. Lrcmux aggregates Musixmatch data via `api.lrcmux.dev` without requiring an API token. Apple Music provides native Apple Music lyrics with per-syllable and per-word timing via the Apple Music API (requires `APPLE_MUSIC_DEVELOPER_TOKEN`).
> If a track has no word-level data on any source, Lyrica automatically falls back to line-level sync so your application flow never breaks.

---

## 📊 JSON Response Schema

### Root Envelope

```json
{
  "status": "success",
  "data": {
    "source": "lrcmux",
    "artist": "Coldplay",
    "title": "Yellow",
    "lyrics": "Look at the stars\nLook how they shine for you...",
    "hasTimestamps": true,
    "sync_level": "word",
    "timestamp": "2026-08-12 14:00:00",
    "timed_lyrics": [ ... ],
    "album": "Parachutes",
    "duration": 267.0
  }
}
```

### Key Envelope Fields

| Field | Type | Description |
|-------|------|-------------|
| `source` | string | Source provider name (typically `"lrcmux"`) |
| `hasTimestamps` | boolean | `true` when timed lyrics are present |
| `sync_level` | string | `"word"` (per-word timing available) or `"line"` (line timing only) or `"syllable"` (per-syllable timing available, Apple Music) |
| `timed_lyrics` | array | Array of synchronized line objects |
| `lyrics` | string | Plain text formatted lyrics (line breaks included) |

---

## 📝 `timed_lyrics` Array Schema

Each element in `timed_lyrics` represents one lyric line with an optional `words` array:

```json
{
  "id": "lrc_0",
  "text": "Look at the stars",
  "start_time": 36189,
  "end_time": 37719,
  "words": [
    { "text": "Look",  "start": 36189, "end": 36546 },
    { "text": " ",     "start": 36546, "end": 36806 },
    { "text": "at",    "start": 36806, "end": 36833 },
    { "text": " ",     "start": 36833, "end": 36943 },
    { "text": "the",   "start": 36943, "end": 37054 },
    { "text": " ",     "start": 37054, "end": 37075 },
    { "text": "stars", "start": 37075, "end": 37719 }
  ]
}
```

### Line Object Properties

| Property | Type | Unit | Description |
|----------|------|------|-------------|
| `id` | string | — | Unique line identifier (e.g., `"lrc_0"`) |
| `text` | string | — | Full textual content of the line |
| `start_time` | integer | milliseconds | Line start timestamp |
| `end_time` | integer | milliseconds | Line end timestamp |
| `words` | array | — | Array of per-word timing entries (present when `sync_level: "word"`) |

### Word Object Properties

| Property | Type | Unit | Description |
|----------|------|------|-------------|
| `text` | string | — | The word or space string |
| `start` | integer | milliseconds | Timestamp when word pronunciation begins |
| `end` | integer | milliseconds | Timestamp when word pronunciation ends |

> [!TIP]
> Space characters (`" "`) are preserved as separate items in the `words` array with their own duration. When rendering karaoke UI elements, filter out entries where `.trim() === ''`.

---

## 💻 Code Examples

### 1. JavaScript / Web (Karaoke Sync Engine)

```javascript
async function fetchKaraokeLyrics(artist, song) {
  const params = new URLSearchParams({
    artist,
    song,
    timestamps: 'true',
    word: 'true'
  });

  const response = await fetch(`http://127.0.0.1:9999/lyrics/?${params}`);
  const json = await response.json();

  if (json.status !== 'success') {
    throw new Error(json.error?.message || 'Failed to fetch lyrics');
  }

  return json.data;
}

// Sync Karaoke Engine
function bindAudioToKaraoke(audioElement, timedLyrics) {
  // Flatten words with line references
  const wordTimeline = timedLyrics.flatMap((line) =>
    (line.words || [])
      .filter((w) => w.text.trim().length > 0)
      .map((w) => ({
        ...w,
        lineId: line.id,
        lineText: line.text
      }))
  );

  audioElement.addEventListener('timeupdate', () => {
    const currentMs = audioElement.currentTime * 1000;
    
    // Find active word
    const activeWord = wordTimeline.find(
      (w) => currentMs >= w.start && currentMs <= w.end
    );

    if (activeWord) {
      console.log(`Active Word: "${activeWord.text}" (Line: ${activeWord.lineId})`);
      // Update UI element highlighting here
    }
  });
}
```

### 2. Python Client

```python
import httpx

def get_karaoke_lyrics(artist: str, song: str) -> dict:
    url = "http://127.0.0.1:9999/lyrics/"
    params = {
        "artist": artist,
        "song": song,
        "timestamps": "true",
        "word": "true"
    }

    with httpx.Client(timeout=15.0) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        res_json = response.json()
        
        if res_json["status"] == "success":
            return res_json["data"]
        else:
            raise Exception(res_json["error"]["message"])

# Usage
data = get_karaoke_lyrics("Coldplay", "Yellow")
print(f"Sync Level: {data.get('sync_level')}")

for line in data["timed_lyrics"]:
    print(f"\nLine [{line['start_time']}ms - {line['end_time']}ms]: {line['text']}")
    for word in line.get("words", []):
        if word["text"].strip():
            print(f"   ↳ {word['start']}ms -> {word['end']}ms : {word['text']}")
```

---

## 🔍 Troubleshooting & Fallback Handling

1. **Check `sync_level` in Response**:
   Always verify `data.sync_level === "word"` before accessing `line.words`. If Musixmatch does not have word-level timestamps for the song, `sync_level` will be `"line"` and `line.words` will not be present.
2. **Force Lrcmux (`sequence=7&pass=true`)**:
   If you strictly require word-level sync and do not want line-level fallbacks from LRCLIB or YouTube, set `sequence=7&pass=true`.
3. **Cache Collisions Prevented**:
   Lyrica includes `word_level` and `syllabus` in its SHA-256 cache key, ensuring line-level, word-level, and syllable-level queries for the same song never overwrite each other in `cache_data/`.

---

## 🎵 Syllable-Level Sync (Apple Music)

Add `&syllabus=true` to request syllable-level synchronized lyrics (Apple Music only):

```bash
GET /lyrics/?artist=Coldplay&song=Yellow&timestamps=true&syllabus=true
```

Syllable-level sync provides timing for **each syllable** within a word, enabling the most granular karaoke experience. The `sync_level` field in the response will be `"syllable"`.

### Syllable Object Schema

Each word in `timed_lyrics[].words` may contain a `syllables` array:

```json
{
  "text": "Look",
  "start": 36189,
  "end": 36546,
  "syllables": [
    { "text": "Look", "start": 36189, "end": 36300 },
    { "text": "ing",  "start": 36300, "end": 36546 }
  ]
}
```

### Sync-Level Fallback Hierarchy

When `timestamps=true` and no `sequence` is specified, Lyrica tries sources in this order:

1. **Syllable-level** (`&syllabus=true`): Apple Music (source 8) — per-syllable timing
2. **Word-level** (`&word=true`): Lrcmux (source 7) + Apple Music (source 8) — per-word timing
3. **Line-level**: All sources — line-level timing
4. **Plain**: All sources except Apple Music — unsynced plain lyrics

Apple Music is always excluded when `timestamps=false` since it does not provide plain text lyrics.
