# Word-Level Sync Guide

Word-level sync is a feature where every **individual word** in a lyric line has its own precise start and end timestamp (in milliseconds). This is different from standard line-level sync where only the whole line gets a timestamp.

Use word-level sync to build:
- **Karaoke apps** — highlight each word as it's sung
- **Lyric animations** — reveal or animate words in real time
- **Accessibility tools** — follow along word by word
- **Learning apps** — track pronunciation timing

> **Source**: Word-level data is provided exclusively by the **Lrcmux source (ID 7)**, which aggregates from Musixmatch. No API token is required.

---

## How to Request Word-Level Sync

Add `&word=true` to any lyrics request alongside `&timestamps=true`:

```
GET /lyrics/?artist=Coldplay&song=Yellow&timestamps=true&word=true
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `timestamps` | bool | `false` | Must be `true` to get any timed lyrics |
| `word` | bool | `false` | When `true`, returns per-word timestamps via Lrcmux |

> Without `&word=true`, setting `&timestamps=true` returns standard **line-level** sync (compatible with all sources).

### Force Lrcmux Only

To ensure you always get word-level data, pin the source to Lrcmux:

```
GET /lyrics/?artist=Coldplay&song=Yellow&timestamps=true&word=true&sequence=7
```

Without `sequence=7`, Lyrica will fall back to other sources if Lrcmux returns no result — those results will be line-level only.

---

## Response Schema

### Full Response Envelope

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
    "timestamp": "2026-08-03 12:00:00",
    "timed_lyrics": [ ... ],
    "album": "Parachute",
    "duration": 267,
    "isrc": "GBDUW0000059"
  }
}
```

### Key fields in `data`

| Field | Type | Description |
|-------|------|-------------|
| `source` | string | Always `"lrcmux"` for word-level responses |
| `hasTimestamps` | bool | `true` when timed_lyrics is present |
| `sync_level` | string | `"word"` or `"line"` — reflects what Musixmatch returned |
| `timed_lyrics` | array | Array of lyric line objects (see below) |
| `lyrics` | string | Plain text version (newline-separated) |

---

## `timed_lyrics` Array Schema

Each element represents one lyric **line**:

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

### Line object fields

| Field | Type | Unit | Description |
|-------|------|------|-------------|
| `id` | string | — | Unique line ID (e.g. `"lrc_0"`) |
| `text` | string | — | Full text of the lyric line |
| `start_time` | int | ms | When this line starts |
| `end_time` | int | ms | When this line ends |
| `words` | array | — | Per-word timing entries (present only when `&word=true`) |

### Word object fields

| Field | Type | Unit | Description |
|-------|------|------|-------------|
| `text` | string | — | The word (or space/punctuation between words) |
| `start` | int | ms | When this word starts |
| `end` | int | ms | When this word ends |

> **Note:** Space characters (`" "`) are included as separate word entries with their own timestamps. Filter them out if you only need actual words.

---

## Availability

Word-level sync depends on whether Musixmatch has word-level data for a track. The API transparently returns what is available:

- `sync_level: "word"` — word-level data was returned, `words` arrays are present
- `sync_level: "line"` — Musixmatch only had line-level data even though `&word=true` was requested
- `sync_level` absent — the response came from a non-lrcmux source

Always check `sync_level` or the presence of the `words` key on individual lines before assuming word-level data is present.

---

## Implementation Examples

### JavaScript / TypeScript

```javascript
async function getLyrics(artist, song) {
  const url = new URL('http://localhost:9999/lyrics/');
  url.searchParams.set('artist', artist);
  url.searchParams.set('song', song);
  url.searchParams.set('timestamps', 'true');
  url.searchParams.set('word', 'true');

  const res = await fetch(url);
  const json = await res.json();

  if (json.status !== 'success') throw new Error(json.error?.message);
  return json.data;
}

// Karaoke highlighting example
function startKaraoke(timedLyrics, audioElement) {
  const allWords = timedLyrics.flatMap((line) =>
    (line.words ?? []).filter(w => w.text.trim()) // skip spaces
      .map(w => ({ ...w, lineId: line.id }))
  );

  audioElement.addEventListener('timeupdate', () => {
    const nowMs = audioElement.currentTime * 1000;
    const active = allWords.find(w => nowMs >= w.start && nowMs <= w.end);
    if (active) highlightWord(active.text, active.lineId);
  });
}
```

### Python

```python
import httpx

def get_word_synced_lyrics(artist: str, song: str) -> dict:
    resp = httpx.get(
        "http://localhost:9999/lyrics/",
        params={"artist": artist, "song": song, "timestamps": "true", "word": "true"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data["status"] != "success":
        raise ValueError(data["error"]["message"])
    return data["data"]

lyrics = get_word_synced_lyrics("Coldplay", "Yellow")

# Print each word with its timing
for line in lyrics["timed_lyrics"]:
    print(f"\n[{line['start_time']}ms] {line['text']}")
    for word in line.get("words", []):
        if word["text"].strip():  # skip spaces
            print(f"  {word['start']:>7}ms → {word['end']:>7}ms  '{word['text']}'")
```

### React (simple karaoke hook)

```tsx
import { useState, useEffect, useRef } from 'react';

interface Word { text: string; start: number; end: number; }
interface Line { id: string; text: string; start_time: number; end_time: number; words?: Word[]; }

function useWordSync(timedLyrics: Line[], audioRef: React.RefObject<HTMLAudioElement>) {
  const [activeWord, setActiveWord] = useState<string | null>(null);
  const [activeLine, setActiveLine] = useState<string | null>(null);

  useEffect(() => {
    if (!audioRef.current) return;
    const audio = audioRef.current;
    const allWords = timedLyrics.flatMap(line =>
      (line.words ?? [])
        .filter(w => w.text.trim())
        .map(w => ({ ...w, lineId: line.id }))
    );

    const onTimeUpdate = () => {
      const nowMs = audio.currentTime * 1000;
      const w = allWords.find(w => nowMs >= w.start && nowMs < w.end);
      setActiveWord(w?.text ?? null);
      setActiveLine(w?.lineId ?? null);
    };

    audio.addEventListener('timeupdate', onTimeUpdate);
    return () => audio.removeEventListener('timeupdate', onTimeUpdate);
  }, [timedLyrics, audioRef]);

  return { activeWord, activeLine };
}
```

---

## Setting a Default

To make word-level sync the default for all requests without passing `&word=true` each time, add this to your `.lyrica.config`:

```ini
[defaults]
timestamps = true
word = true
```

Override per-request with `&word=false` when you need plain line-level sync.

---

## Line-Level vs Word-Level Summary

| Feature | Line-Level (`&timestamps=true`) | Word-Level (`&timestamps=true&word=true`) |
|---|---|---|
| `timed_lyrics` present | ✅ | ✅ |
| `words` arrays in lines | ❌ | ✅ (when available) |
| Sources supported | All 7 sources | Lrcmux only (source 7) |
| Use case | Lyric display, line scrolling | Karaoke, word-by-word highlighting |
| Availability | Very high | Depends on Musixmatch catalog |

---

## Related

- [README.md](README.md) — Project overview and quick start
- [USER_GUIDE.md](USER_GUIDE.md) — Full API reference
- [TRANSLATION_GUIDE.md](TRANSLATION_GUIDE.md) — Translation and romanization
- [.lyrica.config.example](.lyrica.config.example) — Full config reference
