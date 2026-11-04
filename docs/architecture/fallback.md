# Provider Fallback & Sync Degradation

Lyrica features an intelligent provider selection and synchronization-level degradation hierarchy. This guarantees that your application always receives the highest quality lyrics and timestamps available without failing abruptly.

---

## Multi-Sync-Level Fallback Hierarchy

When a client requests granular timing (such as syllable-level or word-level sync), not every song in every catalog will have per-word or per-syllable annotations. Rather than returning an error, Lyrica gracefully degrades down the sync ladder:

```mermaid
graph TD
    Request["Request: timestamps=true & word/syllabus"] --> Phase1{"Phase 1: Syllable Phase<br/>(Apple Music)"}

    Phase1 -- Found --> Done1["Return Syllable-Level Sync<br/>(sync_level: 'syllable')"]
    Phase1 -- Not Found --> Phase2{"Phase 2: Word Phase<br/>(Lrcmux & Apple Music)"}

    Phase2 -- Found --> Done2["Return Word-Level Sync<br/>(sync_level: 'word')"]
    Phase2 -- Not Found --> Lower{"Lower tier allowed?"}

    Lower -- Yes --> Done3["Return best Lrcmux/Apple result<br/>or a richer cached entry"]
    Lower -- No --> Err["404 tier_unavailable"]
```

Normal `timestamps=true` requests use the line phase (LRCLIB, Lrcmux, NetEase, Megalobiz, and Musixmatch when configured). If no synchronized lines exist, the controller returns the best plain-text result from the same chain. Word and syllable requests do **not** fan out to line-only providers.

---

## Fallback Phases in Detail

### Phase 1: Syllable Phase (`&syllabus=true`)
- **Sources**: Apple Music (ID 8).
- **Condition**: Only triggers when `timestamps=true` and `syllabus=true`.
- **Degradation**: If Apple Music does not have syllable-level timing or `APPLE_MUSIC_DEVELOPER_TOKEN` is unset, automatically degrades to Phase 2.

### Phase 2: Word Phase (`&word=true`)
- **Sources**: Lrcmux (ID 7) and Apple Music (ID 8) only.
- **Condition**: Triggers when `timestamps=true` and `word=true` or `syllabus=true`.
- **Degradation**: If neither provider returns the requested tier, Lyrica returns the best lower-tier result already obtained from Lrcmux/Apple Music (or a richer cached entry) when lower tiers are allowed. It does not query line-only providers. With `allow_lower=false` (v2), the response is `404 tier_unavailable`.

### Phase 3: Line Phase (`&timestamps=true`, normal requests)
- **Sources**: LRCLIB (ID 2), Lrcmux (ID 7), NetEase (ID 4), Megalobiz (ID 5), and Musixmatch (ID 6, when configured).
- **Condition**: Triggers for ordinary `timestamps=true` requests, not automatic word/syllabus requests.
- **Degradation**: If no synchronized LRC lines exist anywhere, the controller returns the best plain-text result from the same chain.

### Phase 4: Plain Lyrics Phase
- **Sources**: LRCLIB, Genius (ID 1), NetEase, Megalobiz, and Musixmatch (when configured).
- YouTube Music is temporarily disabled and is not queried.

---

## Sequential vs. Fast Parallel Mode

### Sequential Mode (Default)
Providers are queried one by one in the order specified by the `sequence` parameter (or the default sequence). Execution stops as soon as a provider returns valid lyrics that satisfy the requested sync level.

*Advantage*: Generates the minimum necessary network traffic.

### Fast Parallel Mode (`fast=true`)
When `fast=true`, the Fetch Controller launches concurrent async tasks against all candidates in parallel using `asyncio.as_completed()`. The first provider to respond with valid lyrics wins, and pending requests are cleanly cancelled.

*Advantage*: Minimizes latency by returning the fastest responding provider.

---

## Strict Mode (`pass=true`)

If you want to prevent fallback and enforce that lyrics come **only** from specific providers, set `pass=true` in conjunction with `sequence`:

```http
GET /lyrics/?artist=Queen&song=Bohemian%20Rhapsody&sequence=genius&pass=true
```

In this mode, Lyrica will only query Genius; if Genius does not have the song, it returns `404 Not Found` immediately instead of falling back to LRCLIB or others.
