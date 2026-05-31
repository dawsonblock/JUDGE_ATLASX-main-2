"""Redis caching layer for query results.

This module provides Redis-backed caching for frequently accessed data
like source registry queries, canonical entity lookups,
and review queue snapshots.
"""

from __future__ import annotations

import json
import hashlib
from typing import Any, Callable, TypeVar

from app.core.config import get_settings

T = TypeVar("T")


class RedisCache:
    """Redis-backed cache for query results.

    Provides automatic serialization/deserialization and TTL management.
    Falls back to in-memory caching if Redis is unavailable.
    """

    def __init__(self):
        self._client = None
        self._memory_store: dict[str, tuple[Any, float]] = {}
        settings = get_settings()

        if settings.redis_url:
            try:
                import redis as redis_lib
                self._client = redis_lib.from_url(
                    settings.redis_url,
                    decode_responses=True,
                    socket_connect_timeout=2,
                )
                # Test connection
                self._client.ping()
            except Exception:
                # Fall back to memory if Redis unavailable
                self._client = None

    def _generate_key(self, prefix: str, *args: Any, **kwargs: Any) -> str:
        """Generate a cache key from function arguments.

        Args:
            prefix: Cache key prefix
                (e.g., "source_registry", "canonical_entity")
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Hash-based cache key
        """
        key_parts = [prefix]
        key_parts.extend(str(arg) for arg in args)
        key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
        key_string = ":".join(key_parts)
        # Use SHA256 hash for consistent key length
        return hashlib.sha256(key_string.encode()).hexdigest()

    def get(self, key: str) -> Any | None:
        """Retrieve cached value.

        Args:
            key: Cache key

        Returns:
            Cached value if found and not expired, None otherwise
        """
        if self._client:
            try:
                value = self._client.get(key)
                if value:
                    return json.loads(value)
            except Exception:
                # Fall back to memory on error
                pass

        # Memory fallback with TTL check
        if key in self._memory_store:
            value, expiry = self._memory_store[key]
            import time
            if time.time() < expiry:
                return value
            else:
                # Expired, remove from memory
                del self._memory_store[key]
        return None

    def set(self, key: str, value: Any, ttl_seconds: int = 300) -> bool:
        """Store value in cache.

        Args:
            key: Cache key
            value: Value to cache (must be JSON-serializable)
            ttl_seconds: Time-to-live in seconds (default: 5 minutes)

        Returns:
            True if successful, False otherwise
        """
        if self._client:
            try:
                serialized = json.dumps(value)
                self._client.setex(key, ttl_seconds, serialized)
                return True
            except Exception:
                # Fall back to memory on error
                pass

        # Memory fallback
        import time
        expiry = time.time() + ttl_seconds
        self._memory_store[key] = (value, expiry)
        return True

    def delete(self, key: str) -> bool:
        """Delete value from cache.

        Args:
            key: Cache key

        Returns:
            True if successful, False otherwise
        """
        if self._client:
            try:
                self._client.delete(key)
            except Exception:
                # Fall back to memory on error
                pass

        # Memory fallback
        self._memory_store.pop(key, None)
        return True

    def clear_pattern(self, pattern: str) -> bool:
        """Clear all keys matching a pattern.

        Args:
            pattern: Redis key pattern (e.g., "source_registry:*")

        Returns:
            True if successful, False otherwise
        """
        if self._client:
            try:
                keys = self._client.keys(pattern)
                if keys:
                    self._client.delete(*keys)
                return True
            except Exception:
                # Fall back to memory on error
                pass

        # Memory fallback - clear all keys that start with pattern
        pattern_prefix = pattern.rstrip("*")
        keys_to_delete = [
            k for k in self._memory_store.keys()
            if k.startswith(pattern_prefix)
        ]
        for key in keys_to_delete:
            del self._memory_store[key]
        return True


def cached(
    prefix: str,
    ttl_seconds: int = 300,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator to cache function results in Redis.

    Args:
        prefix: Cache key prefix
        ttl_seconds: Time-to-live in seconds (default: 5 minutes)

    Returns:
        Decorated function with caching

    Example:
        @cached(prefix="source_registry", ttl_seconds=600)
        def get_source_registry():
            # Expensive database query
            return SourceRegistry.query.all()
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args: Any, **kwargs: Any) -> T:
            cache = get_redis_cache()
            key = cache._generate_key(prefix, *args, **kwargs)

            # Try to get from cache
            cached_value = cache.get(key)
            if cached_value is not None:
                return cached_value

            # Execute function and cache result
            result = func(*args, **kwargs)
            cache.set(key, result, ttl_seconds)
            return result

        return wrapper

    return decorator


# Shared cache instance
_redis_cache: RedisCache | None = None


def get_redis_cache() -> RedisCache:
    """Get or create the shared Redis cache instance."""
    global _redis_cache
    if _redis_cache is None:
        _redis_cache = RedisCache()
    return _redis_cache
