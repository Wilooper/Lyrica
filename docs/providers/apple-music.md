# Apple Music Provider (`apple_music`)

Added in Lyrica **v1.5.0**, the Apple Music integration (`src/sources/apple_music_fetcher.py`) connects directly to the Apple Music AMP API to provide the most granular lyrics synchronization available: **syllable-level timing** and **word-level karaoke sync**.

---

## Capabilities

- **Syllable-Level Sync**: Sub-word vocal timing for precision karaoke and pronunciation tracking (`&syllabus=true`).
- **Word-Level Sync**: Per-word timestamps (`&word=true`).
- **Line-Level Sync**: Standard LRC line timestamps (`&timestamps=true`).
- **Rich TTML Parsing**: Parses TTML/XML lyrics trees into JSON line and word structures.

---

## Prerequisites & Configuration

Apple Music requires a Developer Token (JSON Web Token signed with Apple's private key):

```ini
# Apple Music Developer JWT Token (Required for Apple Music source)
APPLE_MUSIC_DEVELOPER_TOKEN=your_jwt_developer_token_here

# Optional: User Music Token (for personalized endpoints)
APPLE_MUSIC_USER_TOKEN=

# Optional: Storefront country code (default: us)
APPLE_STOREFRONT=us

# Optional: Preferred lyrics language and script
APPLE_LYRICS_LANGUAGE=en
APPLE_LYRICS_SCRIPT=latin
```

> [!NOTE]
> If `APPLE_MUSIC_DEVELOPER_TOKEN` is not set, the Apple Music fetcher is automatically disabled during server startup, and Lyrica safely skips it in the fallback sequence without error.

---

## Requesting Apple Music Lyrics

To specifically target Apple Music with syllable sync:

```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Coldplay&song=Yellow&timestamps=true&syllabus=true&sequence=apple_music"
```

To allow Apple Music to fall back to Lrcmux or LRCLIB if syllable timing is unavailable:

```bash
curl "http://127.0.0.1:9999/lyrics/?artist=Coldplay&song=Yellow&timestamps=true&syllabus=true"
```
