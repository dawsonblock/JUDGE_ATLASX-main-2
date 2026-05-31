"""Scoped allowlist for mutation-route authority coverage exceptions.

Each exception must be route+method specific with an owner and expiry note.
Wildcard and broad-prefix exceptions are intentionally disallowed by tests.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AllowlistEntry:
    path: str
    method: str
    reason: str
    owner: str
    expires_on: str


ALLOWLIST: tuple[AllowlistEntry, ...] = (
    AllowlistEntry(
        path="/api/chat/evidence",
        method="POST",
        reason=(
            "Read-only public query endpoint; POST used for payload size/shape, "
            "not for data mutation"
        ),
        owner="backend-platform",
        expires_on="2026-12-31",
    ),
)


def find_allowlist_entry(path: str, method: str) -> AllowlistEntry | None:
    for entry in ALLOWLIST:
        if entry.path == path and entry.method.upper() == method.upper():
            return entry
    return None
