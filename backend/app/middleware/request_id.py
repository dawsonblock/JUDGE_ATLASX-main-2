from __future__ import annotations

import re
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,63}$")


def _canonical_request_id(raw_value: str | None) -> str:
    if raw_value is None:
        return uuid4().hex

    candidate = raw_value.strip()
    if not candidate or not _REQUEST_ID_RE.fullmatch(candidate):
        return uuid4().hex
    return candidate


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a canonical request id to request state and response headers."""

    async def dispatch(self, request: Request, call_next):
        request_id = _canonical_request_id(request.headers.get("X-Request-ID"))
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response