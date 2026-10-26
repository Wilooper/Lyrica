# Community & Streaming Providers

Lyrica integrates multiple community-driven and streaming platform lyrics providers to ensure broad coverage across global and regional catalogs.

---

## 1. LRCLIB (`lrclib`, ID 2)

**Status**: Free, highly reliable, no authentication required.

[LRCLIB](https://lrclib.net/) is an open-source, crowd-sourced synchronized lyrics database. It serves as Lyrica's primary fallback for line-level synced lyrics.

- **Capabilities**: Line-level synchronized LRC lyrics and plain text lyrics.
- **Base URL Override**: `LRCLIB_API_URL` (default: `https://lrclib.net/api/get`).

```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Queen&song=Radio%20Ga%20Ga&sequence=lrclib&timestamps=true"
```

---

## 2. Lrcmux (`lrcmux`, ID 7)

**Status**: Free, no token required.

[Lrcmux](https://api.lrcmux.dev) aggregates synchronized lyrics from Musixmatch and delivers them with **word-level synchronization**.

- **Capabilities**: Line-level timestamps and millisecond-accurate word-level timestamps (`&word=true`).
- **Base URL Override**: `LRCMUX_API_URL` (default: `https://api.lrcmux.dev`).

```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Adele&song=Hello&sequence=lrcmux&timestamps=true&word=true"
```

---

## 3. YouTube Music (`youtube`, ID 3)

**Status**: Free, 3-layer fallback.

Queries YouTube Music and YouTube video transcripts via a 3-layer architecture:
1. `ytmusicapi` for official YouTube Music tracks.
2. `youtube-transcript-api` for automated and community subtitles.
3. `yt-dlp` for raw subtitle extraction.

- **Capabilities**: Line-level timestamps and plain text lyrics.
- **Dedicated Proxy**: Can be configured independently via `YT_PROXY_URL` in `.env`.
- **Cookies / Authentication**: Optional `YT_COOKIES_PATH` to bypass datacenter IP restrictions.

---

## 4. NetEase Cloud Music (`netease`, ID 4)

**Status**: Free, via `syncedlyrics`.

Accesses NetEase's extensive Asian and international music catalog. Particularly effective for J-Pop, K-Pop, C-Pop, and anime soundtrack lyrics.

---

## 5. Megalobiz (`megalobiz`, ID 5)

**Status**: Free, via `syncedlyrics`.

Community-contributed LRC timestamp database with strong coverage of indie, electronic, and regional releases.

---

## 6. Musixmatch (`musixmatch`, ID 6)

**Status**: Requires `MUSIXMATCH_TOKEN`.

Direct connection to the Musixmatch API.
- **Authentication**: `MUSIXMATCH_TOKEN` in `.env`.
- Note: If `MUSIXMATCH_TOKEN` is not set, this provider is skipped. For tokenless Musixmatch data with word-level sync, use **Lrcmux (ID 7)** instead.
