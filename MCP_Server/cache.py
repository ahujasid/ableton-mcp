"""Simple TTL cache for Ableton MCP responses.

Caches read-only responses to avoid redundant socket round-trips.
Automatically invalidated when state-modifying commands are sent.
"""
import time
from typing import Any, Optional


class ResponseCache:
    """TTL-based response cache for read-only Ableton queries"""

    def __init__(self, default_ttl: float = 2.0):
        self._cache: dict = {}
        self.default_ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        """Get a cached value, returning None if expired or missing"""
        if key in self._cache:
            value, expiry = self._cache[key]
            if time.time() < expiry:
                return value
            del self._cache[key]
        return None

    def set(self, key: str, value: Any, ttl: Optional[float] = None):
        """Cache a value with optional custom TTL"""
        self._cache[key] = (value, time.time() + (ttl or self.default_ttl))

    def invalidate(self, prefix: Optional[str] = None):
        """Invalidate cache entries matching a prefix, or all if None"""
        if prefix is None:
            self._cache.clear()
        else:
            keys_to_remove = [k for k in self._cache if k.startswith(prefix)]
            for k in keys_to_remove:
                del self._cache[k]

    def invalidate_all(self):
        """Clear the entire cache"""
        self._cache.clear()
