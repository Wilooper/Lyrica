"""
src/proxy_manager.py

Thread-safe proxy pool with round-robin rotation.

Features:
  - Add/remove proxies at runtime (no restart needed)
  - Round-robin rotation across the proxy pool
  - Mark proxies as failed; auto-retry after cooldown
  - Credential masking — credentials never appear in logs or API responses
  - Optional persistence to the user config file

Supported proxy protocols: http://, https://, socks5://

Usage:
    manager = get_proxy_manager()
    proxy = manager.get_next()       # returns proxy URL string or None
    manager.add("http://host:port")
    manager.remove("http://host:port")
    manager.clear()
    manager.list_masked()            # safe for API responses
"""

import threading
import re
import time
from urllib.parse import urlparse
from src.logger import get_logger

logger = get_logger("proxy_manager")

# How long to quarantine a failed proxy before retrying (seconds)
_FAILURE_COOLDOWN = 60


def _mask_url(url: str) -> str:
    """
    Return proxy URL with credentials replaced by ****:****
    e.g. http://user:pass@host:port → http://****:****@host:port
    """
    try:
        parsed = urlparse(url)
        if parsed.username or parsed.password:
            masked = parsed._replace(
                netloc=f"****:****@{parsed.hostname}:{parsed.port}"
            )
            return masked.geturl()
        return url
    except Exception:
        return "****"


def _validate_proxy(url: str) -> bool:
    """Basic validation that the URL looks like a proxy."""
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https", "socks5") and bool(parsed.hostname)
    except Exception:
        return False


class _ProxyEntry:
    __slots__ = ("url", "masked", "fail_count", "failed_at")

    def __init__(self, url: str):
        self.url       = url
        self.masked    = _mask_url(url)
        self.fail_count = 0
        self.failed_at  = 0.0  # epoch seconds of last failure

    def is_available(self) -> bool:
        if self.fail_count == 0:
            return True
        if time.time() - self.failed_at > _FAILURE_COOLDOWN:
            # Cooldown expired — give it another chance
            self.fail_count = 0
            return True
        return False

    def mark_failure(self):
        self.fail_count += 1
        self.failed_at  = time.time()
        logger.warning(f"Proxy marked as failed: {self.masked} (failures={self.fail_count})")


class ProxyManager:
    """
    Round-robin proxy pool.

    Thread-safe via threading.Lock (used in sync Flask context) and also safe
    from async coroutines since we never block.
    """

    def __init__(self):
        self._proxies: list[_ProxyEntry] = []
        self._index   = 0
        self._lock    = threading.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    def add(self, url: str) -> bool:
        """
        Add a proxy to the pool.

        Returns True if added, False if invalid or already present.
        Credentials are never logged.
        """
        url = url.strip()
        if not _validate_proxy(url):
            logger.warning(f"Rejected invalid proxy URL (scheme must be http/https/socks5)")
            return False

        with self._lock:
            existing_urls = {e.url for e in self._proxies}
            if url in existing_urls:
                logger.info(f"Proxy already in pool: {_mask_url(url)}")
                return False
            self._proxies.append(_ProxyEntry(url))
            logger.info(f"Proxy added: {_mask_url(url)} (pool size={len(self._proxies)})")
            return True

    def remove(self, url: str) -> bool:
        """
        Remove a proxy from the pool by URL.

        Returns True if removed, False if not found.
        """
        url = url.strip()
        with self._lock:
            before = len(self._proxies)
            self._proxies = [e for e in self._proxies if e.url != url]
            removed = len(self._proxies) < before
            if removed:
                logger.info(f"Proxy removed: {_mask_url(url)} (pool size={len(self._proxies)})")
            return removed

    def clear(self) -> int:
        """Remove all proxies. Returns the number removed."""
        with self._lock:
            count = len(self._proxies)
            self._proxies.clear()
            self._index = 0
            logger.info(f"Proxy pool cleared ({count} proxies removed)")
            return count

    def get_next(self) -> str | None:
        """
        Get the next available proxy URL (round-robin).

        Returns None if the pool is empty or all proxies are in cooldown.
        Never raises.
        """
        with self._lock:
            if not self._proxies:
                return None

            # Try all proxies in round-robin order
            start = self._index
            for _ in range(len(self._proxies)):
                entry = self._proxies[self._index % len(self._proxies)]
                self._index = (self._index + 1) % len(self._proxies)
                if entry.is_available():
                    return entry.url

            logger.warning("All proxies are in failure cooldown — proceeding without proxy")
            return None

    def mark_failure(self, url: str):
        """Mark a proxy as failed after a connection error."""
        with self._lock:
            for entry in self._proxies:
                if entry.url == url:
                    entry.mark_failure()
                    return

    def list_masked(self) -> list[dict]:
        """
        Return a list of proxies with credentials masked — safe for API responses.
        """
        with self._lock:
            return [
                {
                    "proxy":      entry.masked,
                    "available":  entry.is_available(),
                    "fail_count": entry.fail_count,
                }
                for entry in self._proxies
            ]

    def size(self) -> int:
        """Return the number of proxies in the pool."""
        with self._lock:
            return len(self._proxies)

    def load_from_list(self, urls: list[str]):
        """Bulk-load proxies from a list (e.g. from config file)."""
        added = 0
        for url in urls:
            if self.add(url):
                added += 1
        logger.info(f"Loaded {added} proxies from config")
        return added


# ─────────────────────────────────────────────────────────────────────────────
# Singleton accessor
# ─────────────────────────────────────────────────────────────────────────────
_instance: ProxyManager | None = None
_lock = threading.Lock()


def get_proxy_manager() -> ProxyManager:
    """Get or create the global proxy manager singleton."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = ProxyManager()
    return _instance
