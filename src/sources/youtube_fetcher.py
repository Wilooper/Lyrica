import asyncio
from datetime import datetime, timezone
from src.logger import get_logger
from .base_fetcher import BaseFetcher, build_result

logger = get_logger("youtube_fetcher")


class YoutubeFetcher(BaseFetcher):
    source_name = "youtube_music"

    # Singleton YTMusic instance — creating it is expensive (network call).
    _ytmusic = None

    @classmethod
    def _get_ytmusic(cls):
        if cls._ytmusic is None:
            try:
                from ytmusicapi import YTMusic
                cls._ytmusic = YTMusic()
                logger.info("YTMusic instance created")
            except Exception as e:
                logger.error(f"Failed to create YTMusic instance: {e}")
        return cls._ytmusic

    # ------------------------------------------------------------------ #
    # Internal: run blocking YTMusic calls in thread pool
    # ------------------------------------------------------------------ #
    async def _run(self, fn, *args, timeout: float = 12.0):
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, fn, *args),
            timeout=timeout,
        )

    # ------------------------------------------------------------------ #
    # Fetch
    # ------------------------------------------------------------------ #
    async def fetch(self, artist: str, song: str, timestamps: bool = False):
        ytmusic = self._get_ytmusic()
        if not ytmusic:
            return None

        try:
            logger.info(f"Attempting YouTube Music for {artist} - {song}")

            # 1. Search
            results = await self._run(
                lambda: ytmusic.search(
                    query=f"{song} {artist}", filter="songs", limit=3
                )
            )
            if not results:
                return None

            # Pick the best result: prefer exact artist match
            artist_lower = artist.lower()
            video_id = None
            for r in results:
                r_artist = " ".join(
                    a.get("name", "") for a in (r.get("artists") or [])
                ).lower()
                if artist_lower in r_artist:
                    video_id = r.get("videoId")
                    break
            if not video_id:
                video_id = results[0].get("videoId")
            if not video_id:
                return None

            # 2. Get watch playlist to find lyrics browse ID
            watch = await self._run(lambda: ytmusic.get_watch_playlist(videoId=video_id))
            browse_id = watch.get("lyrics") if watch else None
            if not browse_id:
                return None

            # 3. Get lyrics
            lyrics_data = await self._run(lambda: ytmusic.get_lyrics(browseId=browse_id))
            if not lyrics_data:
                return None

            raw = lyrics_data.get("lyrics")
            if not raw:
                return None

            # raw can be a string or a list of objects with .text
            if isinstance(raw, str):
                plain_text = raw
                timed = None
            elif isinstance(raw, list):
                plain_text = "\n".join(
                    getattr(line, "text", str(line)) for line in raw
                )
                timed = None
                if timestamps and lyrics_data.get("hasTimestamps"):
                    try:
                        timed = [
                            {
                                "text": getattr(line, "text", ""),
                                "start_time": getattr(line, "start_time", None),
                                "end_time":   getattr(line, "end_time", None),
                                "id":         getattr(line, "line_id", f"yt_{i}"),
                            }
                            for i, line in enumerate(raw)
                        ]
                    except Exception:
                        timed = None
            else:
                return None

            return build_result(
                source="youtube_music",
                artist=artist,
                title=song,
                lyrics=plain_text,
                timed_lyrics=timed,
                has_timestamps=bool(timed),
            )

        except asyncio.TimeoutError:
            logger.warning(f"YouTube Music timeout for {artist} - {song}")
            return None
        except Exception as e:
            logger.error(f"YouTube Music error: {e}")
            return None
