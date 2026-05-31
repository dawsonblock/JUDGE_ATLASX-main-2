"""Redis session storage for JWT tokens and user sessions.

This module provides Redis-backed session storage for JWT tokens,
enabling distributed session management across multiple workers.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.config import get_settings


class RedisSessionStorage:
    """Redis-backed session storage for JWT tokens.

    Stores session data with TTL for automatic expiration.
    Falls back to in-memory storage if Redis is unavailable.
    """

    def __init__(self):
        self._client = None
        self._memory_store: dict[str, Any] = {}
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

    def _get_key(self, session_id: str) -> str:
        """Generate Redis key for session."""
        return f"session:{session_id}"

    def set(
        self,
        session_id: str,
        data: dict[str, Any],
        ttl_seconds: int = 1800,  # 30 minutes default
    ) -> bool:
        """Store session data in Redis or memory.

        Args:
            session_id: Unique session identifier
            data: Session data to store
            ttl_seconds: Time-to-live in seconds

        Returns:
            True if successful, False otherwise
        """
        if self._client:
            try:
                key = self._get_key(session_id)
                value = json.dumps(data)
                self._client.setex(key, ttl_seconds, value)
                return True
            except Exception:
                # Fall back to memory on error
                pass

        # Memory fallback
        self._memory_store[session_id] = data
        return True

    def get(self, session_id: str) -> dict[str, Any] | None:
        """Retrieve session data from Redis or memory.

        Args:
            session_id: Unique session identifier

        Returns:
            Session data if found, None otherwise
        """
        if self._client:
            try:
                key = self._get_key(session_id)
                value = self._client.get(key)
                if value:
                    return json.loads(value)
            except Exception:
                # Fall back to memory on error
                pass

        # Memory fallback
        return self._memory_store.get(session_id)

    def delete(self, session_id: str) -> bool:
        """Delete session from Redis or memory.

        Args:
            session_id: Unique session identifier

        Returns:
            True if successful, False otherwise
        """
        if self._client:
            try:
                key = self._get_key(session_id)
                self._client.delete(key)
            except Exception:
                # Fall back to memory on error
                pass

        # Memory fallback
        self._memory_store.pop(session_id, None)
        return True

    def exists(self, session_id: str) -> bool:
        """Check if session exists in Redis or memory.

        Args:
            session_id: Unique session identifier

        Returns:
            True if session exists, False otherwise
        """
        if self._client:
            try:
                key = self._get_key(session_id)
                return bool(self._client.exists(key))
            except Exception:
                # Fall back to memory on error
                pass

        # Memory fallback
        return session_id in self._memory_store


# Shared session storage instance
_session_storage: RedisSessionStorage | None = None


def get_session_storage() -> RedisSessionStorage:
    """Get or create the shared session storage instance."""
    global _session_storage
    if _session_storage is None:
        _session_storage = RedisSessionStorage()
    return _session_storage
