"""Legacy in-process rate limiter.

Kept for backwards compatibility with deployments that import it directly.
New code should use Flask-Limiter (configured in ``src/app.py``), which
supports Redis-backed counters across workers.

This implementation is thread-safe and prunes idle clients so a long-running
process does not accumulate one deque per source IP forever.
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

REQUEST_LIMIT = int(os.getenv("RATE_LIMIT_PER_MINUTE", "15"))
WINDOW = 60
_MAX_TRACKED_CLIENTS = int(os.getenv("RATE_LIMIT_MAX_CLIENTS", "10000"))

_requests: dict[str, deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def is_rate_limited(ip: str) -> bool:
    """Return True when *ip* has exceeded REQUEST_LIMIT in the last minute."""
    now = time.time()
    with _lock:
        bucket = _requests[ip]
        cutoff = now - WINDOW
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        if len(bucket) >= REQUEST_LIMIT:
            return True

        bucket.append(now)

        # Evict idle clients when the table grows too large. Drop entries whose
        # entire window has expired, then hard-cap the remaining keys if needed.
        if len(_requests) > _MAX_TRACKED_CLIENTS:
            for key in [k for k, v in _requests.items() if not v or v[-1] < cutoff]:
                _requests.pop(key, None)
            while len(_requests) > _MAX_TRACKED_CLIENTS:
                _requests.pop(next(iter(_requests)), None)

        return False
