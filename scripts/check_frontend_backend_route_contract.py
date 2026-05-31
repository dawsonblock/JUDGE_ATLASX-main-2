#!/usr/bin/env python3
"""Validate frontend API call paths against backend and Next.js API routes."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = REPO_ROOT / "frontend"
BACKEND_ROUTES_ROOT = REPO_ROOT / "backend" / "app" / "api" / "routes"
ALLOWLIST_PATH = REPO_ROOT / "scripts" / "route_contract_allowlist.json"

FRONTEND_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}

API_PATH_RE = re.compile(r"/api/[A-Za-z0-9_\-./\[\]{}$:=?&]+")
ROUTER_PREFIX_RE = re.compile(
    r"APIRouter\([^\)]*prefix\s*=\s*[\"']([^\"']+)[\"']"
)
DECORATOR_RE = re.compile(
    r"@router\.(?:get|post|put|patch|delete|options|head)"
    r"\(\s*[\"']([^\"']+)[\"']"
)


def _iter_files(root: Path, *, include_tests: bool = False) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in FRONTEND_EXTENSIONS:
            continue
        parts = set(path.parts)
        if "node_modules" in parts or ".next" in parts or "dist" in parts:
            continue
        if path.name == "middleware.ts":
            continue
        if not include_tests and "tests" in parts:
            continue
        yield path


def _normalize_path(path: str) -> str:
    value = path.strip()
    if not value:
        return ""
    value = value.rstrip("`\"'.,;)")
    api_idx = value.find("/api/")
    if api_idx == -1:
        return ""
    value = value[api_idx:]
    value = value.split("?", 1)[0].split("#", 1)[0]

    # Normalize placeholders from TS template literals and route params.
    value = re.sub(r"\$\{[^}]*\}?", "{param}", value)
    value = re.sub(r"\[[^\]/]+\]", "{param}", value)
    value = re.sub(r":([A-Za-z_][A-Za-z0-9_]*)", "{param}", value)
    value = re.sub(r"\{[^}]+\}", "{param}", value)
    value = value.replace("{param", "{param}")
    while "}}" in value:
        value = value.replace("}}", "}")
    # Query fragments often appear as `${query}` appended directly to a path.
    value = re.sub(r"(?<!/)\{param\}", "", value)

    if "*" in value:
        return ""

    value = re.sub(r"/+", "/", value)
    if value.endswith("/") and value != "/":
        value = value[:-1]
    return value


def _load_allowlist() -> tuple[set[str], list[str]]:
    if not ALLOWLIST_PATH.exists():
        missing = ALLOWLIST_PATH.relative_to(REPO_ROOT)
        return set(), [f"missing allowlist file: {missing}"]

    try:
        payload = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return set(), [f"invalid allowlist JSON: {exc}"]

    errors: list[str] = []
    allowed: set[str] = set()
    if not isinstance(payload, list):
        return set(), ["allowlist must be a JSON array"]

    for idx, item in enumerate(payload):
        if not isinstance(item, dict):
            errors.append(f"allowlist[{idx}] must be an object")
            continue
        path = item.get("path")
        reason = item.get("reason")
        if not isinstance(path, str) or not path.strip():
            errors.append(f"allowlist[{idx}].path must be a non-empty string")
            continue
        if not isinstance(reason, str) or not reason.strip():
            errors.append(
                f"allowlist[{idx}].reason must be a non-empty string"
            )
            continue
        normalized = _normalize_path(path)
        if not normalized:
            errors.append(
                f"allowlist[{idx}].path is not a supported /api path: {path}"
            )
            continue
        allowed.add(normalized)

    return allowed, errors


def _extract_frontend_api_calls() -> dict[str, list[str]]:
    calls: dict[str, list[str]] = {}
    for path in _iter_files(FRONTEND_ROOT):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in API_PATH_RE.finditer(text):
            # Ignore /api-like substrings that are part of identifiers/import
            # paths,
            # such as "@/lib/api/status".
            prior = text[match.start() - 1] if match.start() > 0 else ""
            if prior and re.match(r"[A-Za-z0-9_]", prior):
                continue
            normalized = _normalize_path(match.group(0))
            if not normalized:
                continue
            rel = str(path.relative_to(REPO_ROOT))
            calls.setdefault(normalized, [])
            if rel not in calls[normalized]:
                calls[normalized].append(rel)
    return calls


def _path_matches_pattern(path: str, pattern: str) -> bool:
    expr = "^" + re.escape(pattern).replace(re.escape("{param}"), "[^/]+")
    expr += "$"
    return re.match(expr, path) is not None


def _is_resolved(path: str, patterns: set[str]) -> bool:
    for pattern in patterns:
        if _path_matches_pattern(path, pattern):
            return True
    return False


def _extract_backend_routes() -> set[str]:
    routes: set[str] = set()
    for path in BACKEND_ROUTES_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        prefixes = [m.group(1) for m in ROUTER_PREFIX_RE.finditer(text)]
        if not prefixes:
            prefixes = [""]
        for route_match in DECORATOR_RE.finditer(text):
            route_path = route_match.group(1)
            for prefix in prefixes:
                full = _normalize_path(f"{prefix}{route_path}")
                if full:
                    routes.add(full)
    return routes


def _extract_frontend_internal_api_routes() -> set[str]:
    routes: set[str] = set()
    api_root = FRONTEND_ROOT / "app" / "api"
    if not api_root.exists():
        return routes

    for route_file in api_root.rglob("route.ts"):
        rel = route_file.relative_to(api_root)
        parts = list(rel.parts[:-1])
        normalized_parts = []
        for part in parts:
            if part.startswith("[") and part.endswith("]"):
                normalized_parts.append("{param}")
            else:
                normalized_parts.append(part)
        route = _normalize_path("/api/" + "/".join(normalized_parts))
        if route:
            routes.add(route)
    return routes


def main() -> int:
    allowlist, allowlist_errors = _load_allowlist()
    if allowlist_errors:
        print("RESULT: FAIL")
        for err in allowlist_errors:
            print(f"  - {err}")
        return 1

    frontend_calls = _extract_frontend_api_calls()
    backend_routes = _extract_backend_routes()
    frontend_internal = _extract_frontend_internal_api_routes()

    unresolved: dict[str, list[str]] = {}
    backend_patterns = set(backend_routes)
    frontend_internal_patterns = set(frontend_internal)
    allowlist_patterns = set(allowlist)

    for route, files in sorted(frontend_calls.items()):
        if _is_resolved(route, backend_patterns):
            continue
        if _is_resolved(route, frontend_internal_patterns):
            continue
        if _is_resolved(route, allowlist_patterns):
            continue
        unresolved[route] = files

    if unresolved:
        print("RESULT: FAIL")
        print("Unresolved frontend API paths:")
        for route, files in unresolved.items():
            print(f"  - {route}")
            for f in files:
                print(f"      referenced_in: {f}")
        return 1

    print("RESULT: PASS")
    print(f"  frontend_api_calls_checked: {len(frontend_calls)}")
    print(f"  backend_routes_indexed: {len(backend_routes)}")
    print(f"  frontend_internal_routes_indexed: {len(frontend_internal)}")
    print(f"  allowlist_entries: {len(allowlist)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
