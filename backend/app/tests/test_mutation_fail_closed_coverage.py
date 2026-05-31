"""Enforce fail-closed audit semantics on mutation routes."""

from __future__ import annotations

import ast
from datetime import date
import inspect
import textwrap

from fastapi.routing import APIRoute

from app.main import app
from app.security.mutation_route_allowlist import ALLOWLIST, find_allowlist_entry

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


def _iter_target_mutation_routes() -> list[tuple[str, str, APIRoute]]:
    routes: list[tuple[str, str, APIRoute]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.startswith(TARGET_PREFIXES):
            continue
        for method in sorted((route.methods or set()) & MUTATION_METHODS):
            routes.append((method, route.path, route))
    return routes


def _log_mutation_calls(route: APIRoute) -> list[ast.Call]:
    source = textwrap.dedent(inspect.getsource(route.endpoint))
    tree = ast.parse(source)
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "log_mutation":
            calls.append(node)
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr == "log_mutation":
            calls.append(node)
    return calls


def _has_auditlog_call(route: APIRoute) -> bool:
    source = textwrap.dedent(inspect.getsource(route.endpoint))
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "AuditLog":
            return True
        if isinstance(node.func, ast.Attribute) and node.func.attr == "AuditLog":
            return True
    return False


def _has_append_audit_entry_call(route: APIRoute) -> bool:
    source = textwrap.dedent(inspect.getsource(route.endpoint))
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "append_audit_entry":
            return True
        if isinstance(node.func, ast.Attribute) and node.func.attr == "append_audit_entry":
            return True
    return False


def _has_keyword(call: ast.Call, name: str) -> bool:
    return any(kw.arg == name for kw in call.keywords if kw.arg is not None)


def _has_fail_closed_true(call: ast.Call) -> bool:
    for kw in call.keywords:
        if kw.arg != "fail_closed":
            continue
        return isinstance(kw.value, ast.Constant) and kw.value.value is True
    return False


def _has_db_session_keyword(call: ast.Call) -> bool:
    for kw in call.keywords:
        if kw.arg != "db":
            continue
        return isinstance(kw.value, ast.Name) and kw.value.id == "db"
    return False


def test_all_route_log_mutation_calls_are_fail_closed() -> None:
    findings: list[str] = []

    for method, path, route in _iter_target_mutation_routes():
        if find_allowlist_entry(path, method) is not None:
            continue

        calls = _log_mutation_calls(route)
        has_auditlog = _has_auditlog_call(route)
        has_append_audit = _has_append_audit_entry_call(route)
        if not calls and not has_auditlog and not has_append_audit:
            findings.append(
                f"{method} {path}: missing audit write "
                "(log_mutation, append_audit_entry, or AuditLog)"
            )
            continue

        for idx, call in enumerate(calls, start=1):
            if not _has_keyword(call, "db"):
                findings.append(
                    f"{method} {path}: log_mutation call #{idx} missing db=db"
                )
            elif not _has_db_session_keyword(call):
                findings.append(
                    f"{method} {path}: log_mutation call #{idx} db keyword must pass session variable 'db'"
                )

            if not _has_fail_closed_true(call):
                findings.append(
                    f"{method} {path}: log_mutation call #{idx} missing fail_closed=True"
                )

    assert not findings, "\n".join(findings)


def test_mutation_routes_without_log_mutation_are_audited_or_allowlisted() -> None:
    findings: list[str] = []

    for method, path, route in _iter_target_mutation_routes():
        calls = _log_mutation_calls(route)
        if calls:
            continue
        if _has_auditlog_call(route):
            continue
        if _has_append_audit_entry_call(route):
            continue
        if find_allowlist_entry(path, method) is not None:
            continue
        findings.append(
            f"{method} {path}: missing audit write "
            "(requires log_mutation, append_audit_entry, AuditLog, or allowlist entry)"
        )

    assert not findings, "\n".join(findings)


def test_mutation_audit_allowlist_entries_have_expiry_and_reason() -> None:
    findings: list[str] = []
    for entry in ALLOWLIST:
        if not entry.reason.strip() or len(entry.reason.strip()) < 12:
            findings.append(
                f"allowlist {entry.method} {entry.path}: reason is missing or too vague"
            )
        if not entry.expires_on.strip():
            findings.append(
                f"allowlist {entry.method} {entry.path}: expires_on is required"
            )
            continue
        try:
            date.fromisoformat(entry.expires_on)
        except ValueError:
            findings.append(
                f"allowlist {entry.method} {entry.path}: expires_on must be YYYY-MM-DD"
            )

    assert not findings, "\n".join(findings)


def test_no_expired_mutation_audit_allowlist_entries() -> None:
    findings: list[str] = []
    today = date.today()
    for entry in ALLOWLIST:
        try:
            expiry = date.fromisoformat(entry.expires_on)
        except ValueError:
            continue
        if expiry < today:
            findings.append(
                f"allowlist {entry.method} {entry.path}: entry expired on {entry.expires_on}"
            )

    assert not findings, "\n".join(findings)
