"""
src/sources/musixmatch_fetcher.py

Fetches synced (LRC) or plain lyrics from Musixmatch via the syncedlyrics
library. Token-aware: if MUSIXMATCH_TOKEN is set in the environment, it is
passed to syncedlyrics for authenticated (higher-quality) results. If no
token is set, it falls back gracefully to the unauthenticated mode.

Environment variable:
  MUSIXMATCH_TOKEN  — optional Musixmatch user token.
                      Obtain one from https://developer.musixmatch.com/

Strategy:
  - Read token from env (may be empty/None — that's fine).
  - Ask syncedlyrics for LRC with provider="Musixmatch".
  - Parse LRC into timed_lyrics using the shared parse_lrc() helper.
  - Run syncedlyrics (blocking) in a thread pool to stay async-friendly.
"""

import asyncio
import os
from src.logger import get_logger
from .base_fetcher import BaseFetcher, build_result, parse_lrc

logger = get_logger("musixmatch_fetcher")


class MusixmatchFetcher(BaseFetcher):
    source_name = "musixmatch"

    def __init__(self):
        # Read token at instantiation time — can be empty string or None
        self._token: str | None = os.getenv("MUSIXMATCH_TOKEN") or None
        if self._token:
            logger.info("Musixmatch: using authenticated token from env")
        else:
            logger.info("Musixmatch: no token set, using unauthenticated mode")

    async def fetch(self, artist: str, song: str, timestamps: bool = False):
        query = f"{song} {artist}"
        loop = asyncio.get_event_loop()

        try:
            import syncedlyrics

            logger.info(f"Musixmatch: searching '{query}' (auth={bool(self._token)})")

            def _search():
                # syncedlyrics ≥1.0 accepts enhanced_musixmatch token via
                # the MUSIXMATCH_TOKEN environment variable it reads at call time.
                # We also set it explicitly if present so it takes effect even
                # if the env wasn't set before import.
                if self._token:
                    os.environ.setdefault("MUSIXMATCH_TOKEN", self._token)

                return syncedlyrics.search(
                    query,
                    providers=["Musixmatch"],
                )

            lrc_text = await asyncio.wait_for(
                loop.run_in_executor(None, _search),
                timeout=15.0,
            )

        except asyncio.TimeoutError:
            logger.warning(f"Musixmatch timeout for '{query}'")
            return None
        except ImportError:
            logger.error("syncedlyrics not installed — Musixmatch unavailable")
            return None
        except Exception as e:
            logger.error(f"Musixmatch error: {e}")
            return None

        if not lrc_text:
            logger.info(f"Musixmatch: no result for '{query}'")
            return None

        # ── Determine if result is LRC or plain ────────────────────────────
        is_lrc = "[" in lrc_text and "]" in lrc_text

        timed = None
        if is_lrc:
            timed = parse_lrc(lrc_text)
            plain_text = "\n".join(
                line.split("]", 1)[-1].strip()
                for line in lrc_text.splitlines()
                if "]" in line and line.split("]", 1)[-1].strip()
            )
        else:
            plain_text = lrc_text.strip()

        if not plain_text:
            return None

        use_timed = timed if (timestamps and timed) else None

        return build_result(
            source="musixmatch",
            artist=artist,
            title=song,
            lyrics=plain_text,
            timed_lyrics=use_timed,
            has_timestamps=bool(use_timed),
        )
