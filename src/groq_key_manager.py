"""
src/groq_key_manager.py

Manages multiple Groq API keys with round-robin load distribution
and automatic 24-hour cooldown for failed/expired keys.

Usage:
    from src.groq_key_manager import get_key_manager

    manager = get_key_manager()
    key = manager.get_next_key()  # Returns next healthy key or None
    manager.report_failure(key, 401)  # Quarantine for 24h
    manager.report_rate_limit(key)    # Quarantine for 60s
"""

from __future__ import annotations

import hashlib
import os
import threading
from time import time
from typing import Optional

from src.logger import get_logger

logger = get_logger("groq_key_manager")

# Cooldown durations (seconds)
_AUTH_COOLDOWN = 86400    # 24 hours — invalid / expired key
_RATE_COOLDOWN = 60       # 60 seconds — rate-limited (429)

# HTTP status codes that trigger auth cooldown
_AUTH_ERROR_CODES = {401, 403}


def _mask_key(key: str) -> str:
    """Hash-mask a key for safe logging — never log raw keys."""
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}...{key[-4:]}"


class GroqKeyManager:
    """Thread-safe round-robin key manager with cooldown support."""

    def __init__(self, keys: list[str] | None = None):
        self._lock = threading.Lock()
        self._keys: list[str] = []
        self._pointer: int = 0
        # Maps key → expiry timestamp (when the cooldown lifts)
        self._cooldowns: dict[str, float] = {}

        if keys:
            self._keys = [k.strip() for k in keys if k.strip()]
        else:
            self._load_from_env()

        logger.info(f"GroqKeyManager initialized with {len(self._keys)} key(s)")

    def _load_from_env(self):
        """Load keys from GROQ_API_KEY env var (comma-separated list)."""
        raw = os.getenv("GROQ_API_KEY", "")
        if not raw.strip():
            logger.warning("No GROQ_API_KEY found in environment")
            return
        self._keys = [k.strip() for k in raw.split(",") if k.strip()]

    def _is_healthy(self, key: str) -> bool:
        """Check if a key is not in cooldown."""
        expiry = self._cooldowns.get(key)
        if expiry is None:
            return True
        if time() >= expiry:
            # Cooldown expired — remove it
            del self._cooldowns[key]
            logger.info(f"Key {_mask_key(key)} cooldown expired, back in rotation")
            return True
        return False

    def get_next_key(self) -> Optional[str]:
        """
        Return the next healthy API key using round-robin.

        Returns None if no healthy keys are available.
        """
        with self._lock:
            if not self._keys:
                return None

            total = len(self._keys)
            # Try each key once, starting from the current pointer
            for _ in range(total):
                key = self._keys[self._pointer % total]
                self._pointer = (self._pointer + 1) % total
                if self._is_healthy(key):
                    return key

            logger.error("All Groq API keys are in cooldown")
            return None

    def report_failure(self, key: str, status_code: int):
        """
        Report an API key failure. Quarantine for 24h if it's an
        auth error (401/403). Other errors are logged but not quarantined.
        """
        with self._lock:
            if status_code in _AUTH_ERROR_CODES:
                self._cooldowns[key] = time() + _AUTH_COOLDOWN
                logger.warning(
                    f"Key {_mask_key(key)} quarantined for 24h "
                    f"(status {status_code})"
                )
            else:
                logger.warning(
                    f"Key {_mask_key(key)} failed with status {status_code} "
                    f"(not quarantined)"
                )

    def report_rate_limit(self, key: str):
        """Quarantine a key for 60 seconds due to rate limiting (429)."""
        with self._lock:
            self._cooldowns[key] = time() + _RATE_COOLDOWN
            logger.warning(f"Key {_mask_key(key)} rate-limited, cooldown 60s")

    def get_status(self) -> dict:
        """
        Return key pool status (no raw keys exposed).

        Returns:
            dict with total, healthy, quarantined counts
        """
        with self._lock:
            now = time()
            # Clean up expired cooldowns
            self._cooldowns = {
                k: v for k, v in self._cooldowns.items() if v > now
            }
            healthy = sum(1 for k in self._keys if self._is_healthy(k))
            return {
                "total_keys": len(self._keys),
                "healthy_keys": healthy,
                "quarantined_keys": len(self._keys) - healthy,
                "has_keys": len(self._keys) > 0,
            }

    @property
    def has_keys(self) -> bool:
        """Check if any keys are configured at all."""
        return len(self._keys) > 0


# ── Module-level singleton ──────────────────────────────────────────────────
_MANAGER: GroqKeyManager | None = None
_INIT_LOCK = threading.Lock()


def get_key_manager() -> GroqKeyManager:
    """Get or create the global GroqKeyManager singleton."""
    global _MANAGER
    if _MANAGER is None:
        with _INIT_LOCK:
            if _MANAGER is None:
                _MANAGER = GroqKeyManager()
    return _MANAGER
