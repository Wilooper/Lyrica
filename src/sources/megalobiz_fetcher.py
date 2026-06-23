"""
src/sources/megalobiz_fetcher.py

Fetches synced (LRC) lyrics from Megalobiz via the syncedlyrics library.
Megalobiz is a large user-contributed LRC database with good coverage for
popular Western tracks.

Strategy:
  - Ask syncedlyrics for the LRC string with provider="Megalobiz".
  - Parse LRC into timed_lyrics using the shared parse_lrc() helper.
  - Run syncedlyrics (blocking) in a thread pool to stay async-friendly.
"""

import asyncio
from src.logger import get_logger
from .base_fetcher import BaseFetcher, build_result, parse_lrc

logger = get_logger("megalobiz_fetcher")


class MegalobizFetcher(BaseFetcher):
    source_name = "megalobiz"

    async def fetch(self, artist: str, song: str, timestamps: bool = False):
        query = f"{song} {artist}"
        loop = asyncio.get_event_loop()

        try:
            import syncedlyrics

            logger.info(f"Megalobiz: searching '{query}'")

            lrc_text = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: syncedlyrics.search(
                        query,
                        providers=["Megalobiz"],
                    ),
                ),
                timeout=15.0,
            )

        except asyncio.TimeoutError:
            logger.warning(f"Megalobiz timeout for '{query}'")
            return None
        except ImportError:
            logger.error("syncedlyrics not installed — Megalobiz unavailable")
            return None
        except Exception as e:
            logger.error(f"Megalobiz error: {e}")
            return None

        if not lrc_text:
            logger.info(f"Megalobiz: no result for '{query}'")
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
            source="megalobiz",
            artist=artist,
            title=song,
            lyrics=plain_text,
            timed_lyrics=use_timed,
            has_timestamps=bool(use_timed),
        )
