# Metadata, Trending & Discovery APIs

Lyrica includes dedicated endpoints for audio metadata extraction, autocomplete suggestions, Apple Music trending charts, search query analytics, and JioSaavn audio streaming.

---

## 1. Metadata Only (`GET /metadata/`)

Fetches detailed song metadata without lyrics aggregation. Gathers data asynchronously across iTunes, MusicBrainz, Last.fm, and Wikipedia.

```http
GET /metadata/?artist=Queen&song=Bohemian%20Rhapsody
```

### Query Parameters

| Parameter | Type | Required | Description |
|---|:---:|:---:|---|
| `artist` | string | **Yes** | Artist or band name |
| `song` | string | **Yes** | Track or song title |

### Example Response

```json
{
  "status": "success",
  "data": {
    "title": "Bohemian Rhapsody",
    "artist": "Queen",
    "album": "A Night at the Opera",
    "release_date": "1975-10-31",
    "duration_ms": 354320,
    "artwork_url": "https://is1-ssl.mzstatic.com/image/thumb/Music115/v4/...",
    "primary_genre": "Rock",
    "sources": ["iTunes", "MusicBrainz", "Last.fm", "Wikipedia"],
    "summary": "Bohemian Rhapsody is a song by the British rock band Queen..."
  }
}
```

---

## 2. Search Autocomplete (`GET /suggestion`)

Provides search suggestions as the user types, powered by MusicBrainz search queries.

```http
GET /suggestion?q=Imagine&limit=5
```

### Query Parameters

| Parameter | Type | Required | Default | Description |
|---|:---:|:---:|:---:|---|
| `q` | string | **Yes** | — | Search query string |
| `limit` | integer | No | `10` | Maximum number of suggestions (1–25) |

### Example Response

```json
{
  "status": "success",
  "data": {
    "query": "Imagine",
    "count": 5,
    "suggestions": [
      { "title": "Imagine", "artist": "John Lennon" },
      { "title": "Imagine Dragons", "artist": "Imagine Dragons" },
      { "title": "Imagine", "artist": "Ariana Grande" }
    ]
  }
}
```

---

## 3. Trending Charts (`GET /trending/`)

Retrieves real-time trending tracks aggregated from Apple Music RSS feeds.

```http
GET /trending/?country=US&limit=10
```

### Query Parameters

| Parameter | Type | Required | Default | Description |
|---|:---:|:---:|:---:|---|
| `country` | string | No | `US` | 2-letter ISO country code (`US`, `GB`, `IN`, `BR`, `JP`, `DE`, `FR`, `CA`, `AU`, `MX`) |
| `countries` | string | No | — | Comma-separated country codes (e.g., `US,GB,IN`) |
| `limit` | integer | No | `20` | Maximum songs to return (1–100) |

### Example Response

```json
{
  "status": "success",
  "data": {
    "country": "US",
    "total": 10,
    "songs": [
      {
        "rank": 1,
        "title": "Housewife",
        "artist": "Tate McRae",
        "artwork_url": "https://is1-ssl.mzstatic.com/...",
        "apple_music_url": "https://music.apple.com/..."
      }
    ]
  }
}
```

---

## 4. Query Analytics (`GET /analytics/*`)

Lyrica maintains search query analytics to track trending user interest:

### `GET /analytics/top-queries/`
Lists the most requested queries globally or filtered by country:
```http
GET /analytics/top-queries/?country=US&days=7&limit=15
```

### `GET /analytics/trending-by-country/`
Returns the top queries broken down by country:
```http
GET /analytics/trending-by-country/?limit=5
```

### `GET /analytics/trending-vs-queries/`
Cross-analyzes trending Apple Music charts against user search traffic:
```http
GET /analytics/trending-vs-queries/?country=US&limit=10
```

### `GET /analytics/trending-intersection/`
Identifies songs that appear simultaneously in both trending charts and user search queries.

---

## 5. JioSaavn Audio Search & Stream (`GET /api/jiosaavn/*`)

Integrated streaming endpoints for playable audio streams:

### Search Tracks:
```http
GET /api/jiosaavn/search?q=Bohemian%20Rhapsody
```

### Get Audio Stream:
```http
GET /api/jiosaavn/play?songLink=<song_url_or_token>
```
Returns direct playable audio streaming links (96kbps, 160kbps, 320kbps MP4/AAC).
