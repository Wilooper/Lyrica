"""In-process request coalescing (singleflight).

Flask serves each request on its own thread, so a process-wide map of
``threading.Event`` objects is enough to collapse a cache stampede. When Redis
is available the same idea can be extended cross-worker later; correctness does
not depend on it.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

from src.logger import get_logger

logger = get_logger("singleflight")


class _SingleFlight:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._inflight: dict[str, threading.Event] = {}
        self._leaders = 0
        self._followers = 0
        self._timeouts = 0

    @contextmanager
    def run(self, key: str, timeout: float = 60.0) -> Iterator[bool]:
        """Yield ``True`` for the leader and ``False`` for waiters.

        Followers block until the leader finishes (or the timeout elapses) and
        should re-check the cache afterwards.
        """
        with self._lock:
            event = self._inflight.get(key)
            if event is None:
                event = threading.Event()
                self._inflight[key] = event
                leader = True
                self._leaders += 1
            else:
                leader = False
                self._followers += 1

        if leader:
            try:
                yield True
            finally:
                with self._lock:
                    self._inflight.pop(key, None)
                event.set()
            return

        if not event.wait(timeout):
            self._timeouts += 1
            logger.warning("Singleflight wait timed out for key %s", key[:12])
        yield False

    def stats(self) -> dict:
        with self._lock:
            return {
                "inflight": len(self._inflight),
                "leaders": self._leaders,
                "followers": self._followers,
                "wait_timeouts": self._timeouts,
            }


singleflight = _SingleFlight()
