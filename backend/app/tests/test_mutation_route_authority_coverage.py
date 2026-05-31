"""Mutation-route authority coverage checks.

This suite inspects real FastAPI route objects from the live application
(not static module lists) and enforces actor role-floor dependencies on
mutation endpoints.
"""

from __future__ import annotations

import inspect
from datetime import date
from typing import Iterable

from fastapi.routing import APIRoute

from app.main import app
from app.security.mutation_route_allowlist import ALLOWLIST, find_allowlist_entry


FORBIDDEN_DEPENDENCIES = (
    "require_admin_token",
    "require_system_admin",
    "require_admin_imports",
)

REQUIRED_DEPENDENCIES = (
    "require_import_actor",
    "require_source_admin_actor",
    "require_ai_review_actor",
    "require_admin_actor",
    "require_reviewer_actor",
    "require_public_event_actor",
)

MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
TARGET_PREFIXES = (
    "/api/admin",
    "/api/ingestion",
    "/api/ingest",
    "/api/ai-review",
    "/api/review",
    "/api/sources",
    "/api/evidence",
    "/api/graph",
    "/api/events",
    "/api/chat",
    "/api/evidence-store",
    "/api/map",
)


def _dependency_names(route: APIRoute) -> set[str]:
    names: set[str] = set()
    for dep in route.dependant.dependencies:
        call = dep.call
        if call is None:
            continue
        name = getattr(call, "__name__", None)
        if name:
            names.add(name)
    return names


def _iter_target_mutation_routes() -> Iterable[tuple[str, APIRoute, str]]:
    """Scan all routes in the live FastAPI app for mutation endpoints."""
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.startswith(TARGET_PREFIXES):
            continue
        route_methods = route.methods or set()
        for method in sorted(route_methods & MUTATION_METHODS):
            yield route.path, route, method


def _has_audit_signal(route: APIRoute) -> bool:
    source = inspect.getsource(route.endpoint)
    return (
        "log_mutation(" in source
        or "AuditLog(" in source
        or "append_audit_entry(" in source
    )


def _is_allowlisted(path: str, method: str) -> bool:
    return find_allowlist_entry(path, method) is not None


def test_allowlist_entries_are_specific_and_documented() -> None:
    findings: list[str] = []
    today = date.today()
    for entry in ALLOWLIST:
        if "*" in entry.path or "*" in entry.method:
            findings.append(
                f"allowlist {entry.method} {entry.path}: wildcard not allowed"
            )
        if not entry.path.startswith(TARGET_PREFIXES):
            findings.append(
                f"allowlist {entry.method} {entry.path}: path outside monitored prefixes"
            )
        if not entry.reason.strip():
            findings.append(f"allowlist {entry.method} {entry.path}: missing reason")
        if not entry.owner.strip():
            findings.append(f"allowlist {entry.method} {entry.path}: missing owner")
        if not entry.expires_on.strip():
            findings.append(f"allowlist {entry.method} {entry.path}: missing expires_on")
            continue

        try:
            expiry = date.fromisoformat(entry.expires_on)
        except ValueError:
            findings.append(
                f"allowlist {entry.method} {entry.path}: expires_on must be YYYY-MM-DD"
            )
            continue

        if expiry < today:
            findings.append(
                f"allowlist {entry.method} {entry.path}: entry expired on {entry.expires_on}"
            )

    assert not findings, "\n".join(findings)


def test_mutation_routes_use_explicit_role_floors() -> None:
    findings: list[str] = []
    for module_name, route, method in _iter_target_mutation_routes():
        dep_names = _dependency_names(route)
        route_id = f"{method} {route.path} ({module_name}.{route.endpoint.__name__})"

        for forbidden in FORBIDDEN_DEPENDENCIES:
            if forbidden in dep_names and not _is_allowlisted(route.path, method):
                findings.append(f"{route_id}: forbidden dependency {forbidden}")

        if (
            not any(required in dep_names for required in REQUIRED_DEPENDENCIES)
            and not _is_allowlisted(route.path, method)
        ):
            findings.append(f"{route_id}: missing explicit role-floor helper")

        if not _has_audit_signal(route) and not _is_allowlisted(route.path, method):
            findings.append(
                f"{route_id}: missing audit signal "
                "(log_mutation, append_audit_entry, or AuditLog)"
            )

    assert not findings, "\n".join(findings)
