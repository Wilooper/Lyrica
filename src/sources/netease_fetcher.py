"""
src/sources/netease_fetcher.py

Fetches synced (LRC) or plain lyrics from NetEase Music via the
syncedlyrics library. NetEase has a vast Chinese + international catalog
and returns well-formatted LRC data.

Strategy:
  - Ask syncedlyrics for the LRC string (synced if available, else None).
  - Also try plain lyrics as fallback.
  - Parse LRC into timed_lyrics using the shared parse_lrc() helper.
  - Run syncedlyrics (blocking) in a thread pool to stay async-friendly.
"""

import asyncio
from src.logger import get_logger
from .base_fetcher import BaseFetcher, build_result, parse_lrc

logger = get_logger("netease_fetcher")


class NetEaseFetcher(BaseFetcher):
    source_name = "netease"

    async def fetch(self, artist: str, song: str, timestamps: bool = False):
        query = f"{song} {artist}"
        loop = asyncio.get_event_loop()

        # ── Synced (LRC) attempt ────────────────────────────────────────────
        lrc_text = None
        plain_text = None

        try:
            import syncedlyrics

            logger.info(f"NetEase: searching '{query}'")

            # syncedlyrics.search() is blocking — offload to thread pool
            lrc_text = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: syncedlyrics.search(
                        query,
                        providers=["NetEase"],
                    ),
                ),
                timeout=15.0,
            )

        except asyncio.TimeoutError:
            logger.warning(f"NetEase timeout for '{query}'")
            return None
        except ImportError:
            logger.error("syncedlyrics not installed — NetEase unavailable")
            return None
        except Exception as e:
            logger.error(f"NetEase error: {e}")
            return None

        if not lrc_text:
            logger.info(f"NetEase: no result for '{query}'")
            return None

        # ── Determine if result is LRC or plain ────────────────────────────
        is_lrc = "[" in lrc_text and "]" in lrc_text

        timed = None
        if is_lrc:
            timed = parse_lrc(lrc_text)
            # Strip timestamps for plain lyrics field
            plain_text = "\n".join(
                line.split("]", 1)[-1].strip()
                for line in lrc_text.splitlines()
                if "]" in line and line.split("]", 1)[-1].strip()
            )
        else:
            plain_text = lrc_text.strip()

        if not plain_text:
            return None

        # Use timed lyrics only when requested or when it's the only form
        use_timed = timed if (timestamps and timed) else None

        return build_result(
            source="netease",
            artist=artist,
            title=song,
            lyrics=plain_text,
            timed_lyrics=use_timed,
            has_timestamps=bool(use_timed),
        )
