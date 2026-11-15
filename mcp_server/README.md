# Lyrica MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io/) server for the
**stable Lyrica v1.5.0 REST API**.

This package is an HTTP client wrapper: it does **not** import the Lyrica
application or its fetchers. Point it at any running Lyrica v1.5.0 deployment
(local, Docker, or hosted) and it exposes the public API as MCP tools.

> v2 is still in beta on a separate branch. This server deliberately targets
> the `v1.5.0` tag so clients can integrate against the stable v1 API now.

---

## Tools

| Tool | Lyrica endpoint | Purpose |
|---|---|---|
| `lyrica_get_lyrics` | `GET /lyrics/` | Plain, line, word, or syllable lyrics; translation, romanization, mood, metadata |
| `lyrica_get_metadata` | `GET /metadata/` | Album, artwork, release date, genre, duration, summary |
| `lyrica_search_suggestions` | `GET /suggestion` | MusicBrainz-backed title/artist autocomplete |
| `lyrica_get_trending` | `GET /trending/` | Apple Music RSS charts for one or more countries |
| `lyrica_get_top_queries` | `GET /analytics/top-queries/` | Most requested lyric searches |
| `lyrica_get_trending_by_country` | `GET /analytics/trending-by-country/` | Top searches per country |
| `lyrica_compare_trending_vs_queries` | `GET /analytics/trending-vs-queries/` | Trending charts vs. search traffic |
| `lyrica_get_trending_intersection` | `GET /analytics/trending-intersection/` | Songs in both charts and searches |
| `lyrica_search_jiosaavn` | `GET /api/jiosaavn/search` | JioSaavn track search |
| `lyrica_get_jiosaavn_stream` | `GET /api/jiosaavn/play` | Direct audio stream URLs |
| `lyrica_get_health` | `GET /health`, `/health/ready` | Reachability and dependency health |
| `lyrica_get_cache_stats` | `GET /cache/stats` | Public L1/L2/L3 cache statistics |

The server also exposes two resources (`lyrica://api/info`,
`lyrica://providers`) and two prompts (`fetch_lyrics_prompt`,
`trending_prompt`).

Admin endpoints are intentionally **not** exposed, so the MCP server never
needs `ADMIN_KEY`.

---

## Requirements

- Python 3.11+
- A running Lyrica **v1.5.0** API
- MCP Python SDK 2.3+ (installed automatically)

Start Lyrica first:

```bash
# From the Lyrica v1.5.0 checkout
python run.py                 # http://127.0.0.1:9999
# or
docker compose up -d          # http://localhost:7860
```

---

## Install

```bash
cd mcp_server
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

For development and tests:

```bash
pip install -e ".[test]"
pytest
```

Or run without installing, using `uv` from this directory:

```bash
uv run --with mcp --with httpx python -m lyrica_mcp --base-url http://127.0.0.1:9999
```

---

## Run

### stdio (default)

MCP clients such as Claude Desktop, Cursor, and VS Code launch the server as a
subprocess. The client speaks JSON-RPC over stdin/stdout:

```bash
lyrica-mcp --base-url http://127.0.0.1:9999
```

### Streamable HTTP

For a shared or remote deployment:

```bash
lyrica-mcp \
  --transport streamable-http \
  --host 0.0.0.0 \
  --port 8000 \
  --base-url http://127.0.0.1:9999
```

The endpoint defaults to `http://127.0.0.1:8000/mcp`. Add `--json-response`
if your client prefers plain JSON over SSE responses.

### Connectivity check

```bash
lyrica-mcp --base-url http://127.0.0.1:9999 --check
```

This calls `/health/ready` and prints the response, then exits. It is useful
before wiring the server into a client.

---

## Client configuration

### Claude Desktop

Edit `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "lyrica": {
      "command": "/absolute/path/to/mcp_server/.venv/bin/lyrica-mcp",
      "args": ["--base-url", "http://127.0.0.1:9999"],
      "env": {
        "LYRICA_TIMEOUT": "90"
      }
    }
  }
}
```

### Cursor

`.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "lyrica": {
      "command": "/absolute/path/to/mcp_server/.venv/bin/lyrica-mcp",
      "args": ["--base-url", "http://127.0.0.1:9999"]
    }
  }
}
```

### VS Code

`.vscode/mcp.json`:

```json
{
  "servers": {
    "lyrica": {
      "type": "stdio",
      "command": "/absolute/path/to/mcp_server/.venv/bin/lyrica-mcp",
      "args": ["--base-url", "http://127.0.0.1:9999"]
    }
  }
}
```

### Remote Streamable HTTP

Run the server with `--transport streamable-http`, then point the client at
`http://your-host:8000/mcp`.

---

## Configuration

All flags can also be set through environment variables:

| Variable | Default | Description |
|---|---|---|
| `LYRICA_API_URL` | `http://127.0.0.1:9999` | Lyrica API base URL |
| `LYRICA_TIMEOUT` | `90` | HTTP timeout in seconds (1-600) |
| `LYRICA_MCP_TRANSPORT` | `stdio` | `stdio` or `streamable-http` |
| `LYRICA_MCP_HOST` | `127.0.0.1` | HTTP bind host |
| `LYRICA_MCP_PORT` | `8000` | HTTP port |
| `LYRICA_MCP_PATH` | `/mcp` | Streamable HTTP endpoint path |
| `LYRICA_MCP_JSON_RESPONSE` | `false` | Use JSON instead of SSE for HTTP |
| `LYRICA_MCP_LOG_LEVEL` | `INFO` | Log level (logs go to stderr) |

Copy `.env.example` to `.env` in this directory for local use. The server loads
`mcp_server/.env` (and then `.env` in the current directory) before reading the
environment; real environment variables always take precedence. With MCP
clients, the `env` block in the client configuration is also a portable option.

---

## Docker

Build from this directory:

```bash
docker build -t lyrica-mcp .
```

Run against a Lyrica API on the host:

```bash
docker run --rm -i \
  -e LYRICA_API_URL=http://host.docker.internal:9999 \
  lyrica-mcp
```

For Streamable HTTP:

```bash
docker run --rm -p 8000:8000 \
  -e LYRICA_API_URL=http://host.docker.internal:9999 \
  -e LYRICA_MCP_TRANSPORT=streamable-http \
  -e LYRICA_MCP_HOST=0.0.0.0 \
  lyrica-mcp
```

On Linux, `host.docker.internal` may require
`--add-host=host.docker.internal:host-gateway`, or use your machine's LAN IP.

---

## Response and error behavior

Tool results are the raw Lyrica v1 JSON envelopes, for example:

```json
{
  "status": "success",
  "data": {
    "source": "lrclib",
    "artist": "Coldplay",
    "title": "Yellow",
    "hasTimestamps": false,
    "lyrics": "Look at the stars..."
  }
}
```

Upstream failures become MCP tool errors with the Lyrica HTTP status and
message, for example:

```text
Lyrica API returned HTTP 404 for GET lyrics/: Lyrics not found
```

Validation errors (empty artist, unsupported country, `pass_through` without
`sequence`) also become tool errors before any HTTP request is made.

Lyrica rate-limits requests (15/min in development, 60/min in production by
default). If you see HTTP 429, wait before retrying.

---

## Notes on v1.5.0 behavior

- `word=true` and `syllabus=true` imply `timestamps=true`.
- Word-level requests only route to `lrcmux` and `apple_music`.
- Syllable-level requests require `APPLE_MUSIC_DEVELOPER_TOKEN` and route to
  Apple Music first, then `lrcmux`.
- `translate=true` / `romanize=true` require `GROQ_API_KEY` on the Lyrica
  server. These requests use a minimum 180-second timeout.
- Token-gated providers (`musixmatch`, `apple_music`) are skipped when their
  tokens are not configured.
- MCP tool parameters are sent explicitly, so they override `.lyrica.config`
  defaults on the Lyrica server.

---

## Layout

```
mcp_server/
├── lyrica_mcp/
│   ├── __init__.py      # version and target API version
│   ├── __main__.py      # CLI and transport selection
│   ├── client.py        # httpx wrapper for the v1.5.0 API
│   ├── config.py        # validated environment/CLI settings
│   ├── constants.py     # providers, countries, endpoint metadata
│   ├── operations.py    # validation and tool implementations
│   └── server.py        # MCP tools, resources, prompts
├── tests/
├── Dockerfile
├── pyproject.toml
├── requirements.txt
└── .env.example
```
