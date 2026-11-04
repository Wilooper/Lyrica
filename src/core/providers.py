"""Provider choke point: quota, circuit breaker, bulkhead, and metrics.

Every provider call goes through :func:`try_acquire` and :func:`slot` so a
single slow, broken, or lying provider cannot hurt the rest of the system.
The default backend is in-process and dependency-free; Redis-backed quotas can
be layered on later without changing callers.
"""

from __future__ import annotations

import asyncio
import os
import re
import threading
import time
import weakref
from collections import deque

from src.logger import get_logger

logger = get_logger("providers")

# Real limits belong in provider documentation. These are conservative
# defaults that can be overridden per deployment via .lyrica.config or env.
_DEFAULT_RPM = {
    "genius": 5,
    "lrclib": 30,
    "youtube": 10,
    "netease": 20,
    "megalobiz": 15,
    "musixmatch": 15,
    "lrcmux": 30,
    "apple_music": 10,
}

_SAFETY_FACTOR = 0.85
_BREAKER_THRESHOLD = max(1, int(os.getenv("LYRICA_BREAKER_THRESHOLD", "5")))
_BREAKER_COOLDOWN = max(1.0, float(os.getenv("LYRICA_BREAKER_COOLDOWN", "30")))
_BREAKER_GOOD_PROBES = max(1, int(os.getenv("LYRICA_BREAKER_GOOD_PROBES", "2")))
_DEFAULT_CONCURRENCY = max(1, int(os.getenv("LYRICA_PROVIDER_CONCURRENCY", "8")))

_DISABLED = {
    name.strip().lower()
    for name in os.getenv("LYRICA_DISABLED_PROVIDERS", "").split(",")
    if name.strip()
}

_SECRET_RE = re.compile(
    r"(?i)\b(access_?token|api_?key|auth(?:orization)?|password|secret|token|key)"
    r"\b(\s*[=:]\s*)[^\s&,;\"']+"
)
_BEARER_RE = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]+")


def redact(value) -> str:
    """Remove credential-looking substrings before logging or exposing errors."""
    text = str(value or "")
    text = _BEARER_RE.sub(r"\1<redacted>", text)
    return _SECRET_RE.sub(r"\1\2<redacted>", text)


_RPM_ATTR = {
    "genius": "genius_rpm",
    "lrclib": "lrclib_rpm",
    "youtube": "youtube_rpm",
    "netease": "netease_rpm",
    "megalobiz": "megalobiz_rpm",
    "musixmatch": "musixmatch_rpm",
    "lrcmux": "lrcmux_rpm",
    "apple_music": "apple_music_rpm",
}


def _configured_rpm(name: str) -> int:
    env_key = f"LYRICA_PROVIDER_{name.upper()}_RPM"
    raw = os.getenv(env_key)
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    try:
        from src.user_config import get_user_config

        cfg = get_user_config()
        attr = _RPM_ATTR.get(name)
        if attr:
            return max(1, int(getattr(cfg, attr, _DEFAULT_RPM.get(name, 10))))
    except Exception:
        pass
    return _DEFAULT_RPM.get(name, 10)


class _ProviderState:
    __slots__ = (
        "name",
        "lock",
        "capacity",
        "tokens",
        "refill",
        "updated",
        "failures",
        "breaker",
        "opened_at",
        "good_probes",
        "probe_inflight",
        "successes",
        "errors",
        "not_found",
        "rejected",
        "latencies",
        "last_error",
        "last_latency",
        "concurrency",
    )

    def __init__(self, name: str) -> None:
        self.name = name
        self.lock = threading.Lock()
        rpm = _configured_rpm(name)
        self.capacity = max(1.0, rpm * _SAFETY_FACTOR)
        self.tokens = self.capacity
        self.refill = self.capacity / 60.0
        self.updated = time.monotonic()
        self.failures = 0
        self.breaker = "closed"  # closed | open | half_open
        self.opened_at = 0.0
        self.good_probes = 0
        self.probe_inflight = False
        self.successes = 0
        self.errors = 0
        self.not_found = 0
        self.rejected = 0
        self.latencies: deque[float] = deque(maxlen=128)
        self.last_error = ""
        self.last_latency = 0.0
        try:
            self.concurrency = max(1, int(os.getenv(f"LYRICA_PROVIDER_{name.upper()}_CONCURRENCY", _DEFAULT_CONCURRENCY)))
        except ValueError:
            self.concurrency = _DEFAULT_CONCURRENCY

    # ── quota ────────────────────────────────────────────────────────────
    def _refill_locked(self, now: float) -> None:
        elapsed = max(0.0, now - self.updated)
        if elapsed:
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill)
            self.updated = now

    # ── breaker ──────────────────────────────────────────────────────────
    def _breaker_allows_locked(self, now: float) -> bool:
        if self.breaker == "closed":
            return True
        if self.breaker == "open":
            if now - self.opened_at < _BREAKER_COOLDOWN:
                return False
            self.breaker = "half_open"
            self.good_probes = 0
            self.probe_inflight = False
        if self.breaker == "half_open":
            if self.probe_inflight:
                return False
            self.probe_inflight = True
        return True

    def try_acquire(self) -> tuple[bool, str]:
        if self.name in _DISABLED:
            return False, "disabled"
        now = time.monotonic()
        with self.lock:
            if not self._breaker_allows_locked(now):
                return False, "breaker_open"
            self._refill_locked(now)
            if self.tokens < 1.0:
                return False, "quota_exhausted"
            self.tokens -= 1.0
        return True, "ok"

    def record_success(self, latency: float, *, not_found: bool = False) -> None:
        with self.lock:
            self.successes += 1
            if not_found:
                self.not_found += 1
            self.failures = 0
            self.last_latency = latency
            self.latencies.append(latency)
            self._record_probe_success_locked()

    def record_failure(self, error: str = "") -> None:
        with self.lock:
            self.errors += 1
            self.failures += 1
            self.last_error = redact(error)[:200]
            if self.breaker == "half_open":
                self.breaker = "open"
                self.opened_at = time.monotonic()
                self.probe_inflight = False
            elif self.failures >= _BREAKER_THRESHOLD:
                self.breaker = "open"
                self.opened_at = time.monotonic()
                logger.warning(
                    "Circuit breaker OPEN for %s after %d failures (last: %s)",
                    self.name,
                    self.failures,
                    self.last_error,
                )

    def _record_probe_success_locked(self) -> None:
        if self.breaker == "half_open":
            self.probe_inflight = False
            self.good_probes += 1
            if self.good_probes >= _BREAKER_GOOD_PROBES:
                self.breaker = "closed"
                self.good_probes = 0

    def record_rejected(self, reason: str) -> None:
        with self.lock:
            self.rejected += 1
            self.last_error = f"rejected: {reason}"[:200]
            # The provider answered, it just answered about the wrong song.
            # That still proves it is reachable, so let it close the breaker.
            self._record_probe_success_locked()

    def record_aborted(self) -> None:
        """Release a half-open probe slot when the caller is cancelled."""
        with self.lock:
            if self.breaker == "half_open":
                self.probe_inflight = False

    def snapshot(self) -> dict:
        with self.lock:
            latencies = sorted(self.latencies)
            count = len(latencies)
            p50 = latencies[count // 2] if count else 0.0
            p95 = latencies[min(count - 1, int(count * 0.95))] if count else 0.0
            return {
                "state": self.breaker,
                "disabled": self.name in _DISABLED,
                "rpm_capacity": round(self.capacity, 1),
                "tokens": round(self.tokens, 2),
                "successes": self.successes,
                "errors": self.errors,
                "not_found": self.not_found,
                "rejected": self.rejected,
                "consecutive_failures": self.failures,
                "p50_ms": round(p50 * 1000, 1),
                "p95_ms": round(p95 * 1000, 1),
                "last_error": self.last_error,
            }


_STATES: dict[str, _ProviderState] = {}
_STATES_LOCK = threading.Lock()

# One bulkhead per provider per event loop. Each Flask worker thread owns a
# loop, so this bounds concurrency without ever blocking a loop.
_SEMAPHORES: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, asyncio.Semaphore]]" = (
    weakref.WeakKeyDictionary()
)
_SEM_LOCK = threading.Lock()


def get_state(name: str) -> _ProviderState:
    state = _STATES.get(name)
    if state is None:
        with _STATES_LOCK:
            state = _STATES.get(name)
            if state is None:
                state = _ProviderState(name)
                _STATES[name] = state
    return state


def try_acquire(name: str) -> tuple[bool, str]:
    return get_state(name).try_acquire()


def available(name: str) -> bool:
    if name in _DISABLED:
        return False
    state = get_state(name)
    now = time.monotonic()
    with state.lock:
        if state.breaker == "open" and now - state.opened_at < _BREAKER_COOLDOWN:
            return False
        state._refill_locked(now)
        return state.tokens >= 1.0


def _semaphore(name: str) -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    with _SEM_LOCK:
        per_loop = _SEMAPHORES.get(loop)
        if per_loop is None:
            per_loop = {}
            _SEMAPHORES[loop] = per_loop
        sem = per_loop.get(name)
        if sem is None:
            sem = asyncio.Semaphore(get_state(name).concurrency)
            per_loop[name] = sem
        return sem


class _Slot:
    __slots__ = ("name", "sem")

    def __init__(self, name: str) -> None:
        self.name = name
        self.sem = None

    async def __aenter__(self):
        self.sem = _semaphore(self.name)
        await self.sem.acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.sem is not None:
            self.sem.release()


def slot(name: str) -> _Slot:
    """Async context manager bounding in-flight calls per provider/loop."""
    return _Slot(name)


def record_success(name: str, latency: float, *, not_found: bool = False) -> None:
    get_state(name).record_success(latency, not_found=not_found)


def record_failure(name: str, error: str = "") -> None:
    get_state(name).record_failure(error)


def record_rejected(name: str, reason: str) -> None:
    get_state(name).record_rejected(reason)


def record_aborted(name: str) -> None:
    get_state(name).record_aborted()


def snapshot() -> dict[str, dict]:
    return {name: state.snapshot() for name, state in sorted(_STATES.items())}


def reset() -> None:
    """Test helper: forget every provider state."""
    with _STATES_LOCK:
        _STATES.clear()
    with _SEM_LOCK:
        _SEMAPHORES.clear()
