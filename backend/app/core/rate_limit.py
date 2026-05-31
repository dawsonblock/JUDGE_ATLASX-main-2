"""Rate limiting configuration for JudgeTracker Atlas.

This module provides a simple in-memory rate limiter that enforces per-IP limits.
Rate limiting is enabled by default but can be disabled via JTA_RATE_LIMIT_ENABLED=false.

Supports:
- In-memory backend (default, single-process)
- Redis backend when JTA_RATE_LIMIT_BACKEND=redis and JTA_REDIS_URL is set
- Trusted proxy IP list: X-Forwarded-For is only trusted from IPs in JTA_TRUSTED_PROXY_IPS
"""

from __future__ import annotations
from collections import defaultdict
from time import time

from fastapi import HTTPException, Request

from app.core.config import get_settings


class SimpleRateLimiter:
    """Simple in-memory rate limiter using sliding window.
    
    This is a deterministic implementation suitable for alpha/prototype use.
    For production, use Redis-backed rate limiting.
    """
    
    def __init__(self):
        # Store request timestamps per key: {key: [timestamp1, timestamp2, ...]}
        self.requests = defaultdict(list)
    
    def check(self, key: str, limit: int, window: int = 60) -> bool:
        """Check if request should be allowed.
        
        Args:
            key: Unique identifier for the rate limit bucket (e.g., IP address)
            limit: Maximum number of requests allowed
            window: Time window in seconds (default 60)
            
        Returns:
            True if request is allowed, False if limit exceeded
        """
        now = time()
        
        # Remove old requests outside the window
        self.requests[key] = [t for t in self.requests[key] if now - t < window]
        
        # Check if limit exceeded
        if len(self.requests[key]) >= limit:
            return False
        
        # Record this request
        self.requests[key].append(now)
        return True
    
    def reset(self, key: str | None = None) -> None:
        """Reset rate limit for a specific key or all keys.
        
        Args:
            key: Specific key to reset, or None to reset all
        """
        if key:
            self.requests[key] = []
        else:
            self.requests.clear()


class RedisRateLimiter:
    """Redis-backed sliding window rate limiter.

    Uses a sorted set per bucket key with timestamps as scores.
    The allow/deny decision is made atomically via a Lua script so that
    concurrent requests cannot simultaneously observe the same count and
    all be permitted beyond the configured limit.

    Falls back silently to allowing the request if Redis is unavailable.
    """

    # Atomic Lua script: trim expired members, count, conditionally add.
    # KEYS[1]  = sorted-set key
    # ARGV[1]  = current timestamp (float, as string)
    # ARGV[2]  = window start timestamp (float, as string)
    # ARGV[3]  = limit (integer, as string)
    # ARGV[4]  = TTL for the key in seconds (integer, as string)
    # ARGV[5]  = unique member string (timestamp + random suffix)
    # Returns 1 if the request is allowed, 0 if rate-limited.
    _LUA_SCRIPT = """
local key        = KEYS[1]
local now        = tonumber(ARGV[1])
local win_start  = tonumber(ARGV[2])
local lim        = tonumber(ARGV[3])
local ttl        = tonumber(ARGV[4])
local member     = ARGV[5]
redis.call('ZREMRANGEBYSCORE', key, '-inf', win_start)
local count = redis.call('ZCARD', key)
if count >= lim then
    return 0
end
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, ttl)
return 1
"""

    def __init__(self, redis_url: str):
        import redis as redis_lib
        self._client = redis_lib.from_url(redis_url, decode_responses=True)
        self._script = self._client.register_script(self._LUA_SCRIPT)

    def check(self, key: str, limit: int, window: int = 60) -> bool:
        import os as _os
        import time as time_mod
        from app.core.config import get_settings
        
        now = time_mod.time()
        window_start = now - window
        # Generate the unique member ID *outside* the Redis try-block so that
        # an os.urandom() failure surfaces as a real error rather than being
        # silently swallowed as if it were a Redis connectivity issue.
        member = f"{now:.6f}:{_os.urandom(4).hex()}"
        try:
            result = self._script(
                keys=[key],
                args=[str(now), str(window_start), str(limit), str(window + 1), member],
            )
            return bool(result)
        except Exception:
            # On Redis error, fail closed in production, fail open in development
            settings = get_settings()
            if settings.app_env == "production":
                raise HTTPException(
                    status_code=503,
                    detail="Rate limiter unavailable",
                )
            # In development, allow the request
            return True

    def reset(self, key: str | None = None) -> None:
        try:
            if key:
                self._client.delete(key)
            # Global reset not implemented for Redis (would need key scanning)
        except Exception:
            pass


# Shared limiter instance
_limiter: SimpleRateLimiter | RedisRateLimiter | None = None


def get_rate_limiter() -> SimpleRateLimiter | RedisRateLimiter:
    """Get or create the shared rate limiter instance."""
    global _limiter
    if _limiter is None:
        settings = get_settings()
        if settings.rate_limit_backend == "redis" and settings.redis_url:
            try:
                _limiter = RedisRateLimiter(settings.redis_url)
            except Exception:
                # Fall back to in-memory if Redis init fails
                _limiter = SimpleRateLimiter()
        else:
            _limiter = SimpleRateLimiter()
    return _limiter


def _get_client_ip(request: Request) -> str:
    """Determine the real client IP, trusting X-Forwarded-For only from trusted proxies."""
    settings = get_settings()
    trusted_ips = {ip.strip() for ip in settings.trusted_proxy_ips.split(",") if ip.strip()}

    direct_ip = (request.client.host if request.client else None) or "unknown"

    if trusted_ips and direct_ip in trusted_ips:
        # Direct connection is from a trusted proxy — use X-Forwarded-For
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Use the leftmost IP (original client)
            return forwarded_for.split(",")[0].strip()

    # Not from a trusted proxy — use direct connection IP
    return direct_ip


def _check_rate_limit(request: Request, limit_key: str) -> None:
    """Check rate limit for the given key.
    
    Raises HTTPException(429) if limit is exceeded.
    
    Args:
        request: FastAPI Request object
        limit_key: Key to look up in settings (e.g., "public", "admin")
    """
    settings = get_settings()
    
    # Rate limiting disabled in settings
    if not settings.rate_limit_enabled:
        return
    
    # Get limit from settings
    limit = getattr(settings, f"rate_limit_{limit_key}", 60)
    
    ip = _get_client_ip(request)
    
    # Check limit with separate buckets per limit_key
    bucket_key = f"{limit_key}:{ip}"
    limiter = get_rate_limiter()
    if not limiter.check(bucket_key, limit):
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded for {limit_key}: {limit} requests per minute"
        )


# Rate limiting dependencies that actually enforce limits
async def rate_limit_public(request: Request):
    """Enforce public endpoint rate limit (100/min default)."""
    _check_rate_limit(request, "public")


async def rate_limit_admin(request: Request):
    """Enforce admin endpoint rate limit (30/min default)."""
    _check_rate_limit(request, "admin")


async def rate_limit_map(request: Request):
    """Enforce map endpoint rate limit (60/min default)."""
    _check_rate_limit(request, "map")


async def rate_limit_ingestion(request: Request):
    """Enforce ingestion endpoint rate limit (10/min default)."""
    _check_rate_limit(request, "ingestion")

