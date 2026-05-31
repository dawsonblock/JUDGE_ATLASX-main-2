"""Extract actor identity from a FastAPI Request for audit logging."""
from __future__ import annotations

from fastapi import Request


def actor_from_request(request: Request, *, role: str | None = None) -> dict:
    """Return a dict of actor fields extracted from the request.

    The dict can be passed directly to ``append_audit_entry`` as kwargs.
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    ip = (forwarded_for.split(",")[0].strip() if forwarded_for else None) or (
        request.client.host if request.client else None
    )
    return {
        "actor_ip": ip,
        "actor_type": "admin",
        "actor_role": role,
        "user_agent": request.headers.get("User-Agent"),
        "request_id": request.headers.get("X-Request-ID"),
    }
