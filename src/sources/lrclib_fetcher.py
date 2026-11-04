"""
src/sources/lrclib_fetcher.py

Fetches synced or plain lyrics from LRCLIB (https://lrclib.net).

The hot path is a single ``/api/get`` request against the shared keep-alive
connection pool. ``/api/search`` is only used as a fallback, and its results
are scored so a wrong first hit is never selected blindly.
"""

from datetime import datetime, timezone

import httpx

from src.config import LRCLIB_API_URL
from src.core.verifier import score_candidate
from src.logger import get_logger
from .base_fetcher import BaseFetcher, get_http_client, parse_lrc

logger = get_logger("lrclib_fetcher")

_LRCLIB_SEARCH = LRCLIB_API_URL.rsplit("/", 1)[0] + "/search" if LRCLIB_API_URL.endswith("/get") else "https://lrclib.net/api/search"
_UA = "Lyrica/1.0 (https://github.com/Wilooper/Lyrica)"
_MIN_CANDIDATE_SCORE = 0.45


class LRCLIBFetcher(BaseFetcher):
    source_name = "lrclib"

    async def fetch(self, artist: str, song: str, timestamps: bool = True, proxy: str | None = None):
        """Fetch lyrics from LRCLIB.

        ``proxy`` is only used when explicitly supplied; the default path
        reuses the process-wide pooled client.
        """
        logger.info("LRCLIB: fetching '%s – %s' (timestamps=%s)", artist, song, timestamps)
        if proxy:
            async with httpx.AsyncClient(
                proxy=proxy,
                timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=2.0),
                headers={"User-Agent": _UA},
                follow_redirects=True,
            ) as client:
                return await self._fetch_with_client(client, artist, song, timestamps)
        return await self._fetch_with_client(get_http_client(), artist, song, timestamps)

    async def _get(self, client: httpx.AsyncClient, params: dict) -> dict | None:
        """GET /api/get with one cheap retry for flaky keep-alive connections."""
        for attempt in range(2):
            try:
                response = await client.get(LRCLIB_API_URL, params=params)
                if response.status_code == 200:
                    data = response.json()
                    return data if isinstance(data, dict) else None
                if response.status_code in (400, 404):
                    return None
                logger.warning("LRCLIB get returned %s", response.status_code)
            except httpx.TimeoutException:
                logger.warning("LRCLIB get timed out (attempt %d)", attempt + 1)
            except httpx.HTTPError as exc:
                logger.warning("LRCLIB get transport error: %s", exc)
            except ValueError:
                return None
        return None

    async def _search(self, client: httpx.AsyncClient, artist: str, song: str) -> list:
        try:
            response = await client.get(
                _LRCLIB_SEARCH,
                params={"track_name": song, "artist_name": artist},
            )
            if response.status_code != 200:
                logger.warning("LRCLIB search returned %s", response.status_code)
                return []
            results = response.json()
            return results if isinstance(results, list) else []
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("LRCLIB search failed: %s", exc)
            return []

    async def _fetch_with_client(
        self,
        client: httpx.AsyncClient,
        artist: str,
        song: str,
        timestamps: bool,
    ) -> dict | None:
        try:
            # ── Fast path: exact metadata lookup (one request) ───────────────
            data = await self._get(client, {"track_name": song, "artist_name": artist})

            # ── Fallback: search, score candidates, then fetch the best one ──
            if data is None:
                candidates = await self._search(client, artist, song)
                if not candidates:
                    logger.info("LRCLIB: no results found")
                    return None
                ranked = sorted(
                    (
                        (score_candidate(artist, song, candidate), candidate)
                        for candidate in candidates
                        if isinstance(candidate, dict)
                    ),
                    key=lambda item: item[0],
                    reverse=True,
                )
                for score, candidate in ranked[:3]:
                    if score < _MIN_CANDIDATE_SCORE:
                        break
                    data = await self._get(
                        client,
                        {
                            "track_name": candidate.get("trackName") or song,
                            "artist_name": candidate.get("artistName") or artist,
                            "album_name": candidate.get("albumName"),
                            "duration": candidate.get("duration"),
                        },
                    )
                    if data is not None:
                        break

            if data is None:
                return None

            duration_ms = None
            if isinstance(data.get("duration"), (int, float)):
                duration_ms = int(float(data["duration"]) * 1000)

            synced = data.get("syncedLyrics")
            plain = data.get("plainLyrics")
            timed = parse_lrc(synced, duration_ms) if timestamps and synced else []

            if timed:
                # Keep the clean text alongside the timing data.
                lyrics = plain or "\n".join(entry["text"] for entry in timed)
            elif plain:
                lyrics = plain
            elif synced:
                # Plain request or unparseable LRC: strip the timestamp tags.
                parsed = parse_lrc(synced, duration_ms)
                lyrics = "\n".join(entry["text"] for entry in parsed) if parsed else synced
            else:
                logger.info("LRCLIB: no lyrics content in response")
                return None

            result = {
                "source": "lrclib",
                "artist": data.get("artistName"),
                "title": data.get("trackName"),
                "album": data.get("albumName"),
                "duration": data.get("duration"),
                "instrumental": data.get("instrumental", False),
                "lyrics": lyrics,
                "hasTimestamps": bool(timed),
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            }
            if timed:
                result["timed_lyrics"] = timed

            logger.info("LRCLIB: success (hasTimestamps=%s)", result["hasTimestamps"])
            return result

        except Exception as e:
            logger.error("LRCLIB error: %s", e)
            return None
