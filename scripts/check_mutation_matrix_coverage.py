#!/usr/bin/env python3
"""Check mutation route count versus RBAC matrix coverage.

This gate compares:
- count of live admin mutation routes in the FastAPI app with role-floor deps
- count of explicit matrix entries in test_mutation_rbac_matrix.py

It intentionally uses conservative thresholds so the gate remains stable while
still catching accidental matrix deletions.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.routing import APIRoute

from app.main import app

MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
ROLE_HELPERS = {
    "require_import_actor",
    "require_source_admin_actor",
    "require_ai_review_actor",
    "require_admin_actor",
    "require_reviewer_actor",
    "require_admin_review",
    "require_public_event_actor",
    "require_admin_imports",
    "require_admin_token",
}

MATRIX_TEST_FILE = Path("backend/app/tests/test_mutation_rbac_matrix.py")
MIN_MATRIX_CASES = 6
MIN_COVERAGE_RATIO = 0.05


def _route_dependency_names(route: APIRoute) -> set[str]:
    names: set[str] = set()
    for dep in route.dependant.dependencies:
        call = dep.call
        if call is None:
            continue
        name = getattr(call, "__name__", None)
        if name:
            names.add(name)
    return names


def _admin_role_protected_mutation_routes() -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.startswith("/api/admin"):
            continue
        deps = _route_dependency_names(route)
        if not (deps & ROLE_HELPERS):
            continue
        for method in sorted((route.methods or set()) & MUTATION_METHODS):
            routes.add((method, route.path))
    return routes


def _matrix_endpoint_cases() -> set[tuple[str, str]]:
    if not MATRIX_TEST_FILE.exists():
        raise SystemExit(f"FAIL: missing matrix test file: {MATRIX_TEST_FILE}")

    tree = ast.parse(MATRIX_TEST_FILE.read_text(encoding="utf-8"))
    cases: set[tuple[str, str]] = set()

    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "TestAnonymousDenied":
            continue
        for item in node.body:
            if not isinstance(item, ast.Assign):
                continue
            if not any(isinstance(t, ast.Name) and t.id == "MUTATION_ENDPOINTS" for t in item.targets):
                continue
            if not isinstance(item.value, (ast.List, ast.Tuple)):
                continue
            for elt in item.value.elts:
                if not isinstance(elt, ast.Tuple) or len(elt.elts) < 2:
                    continue
                method_node, path_node = elt.elts[0], elt.elts[1]
                if isinstance(method_node, ast.Constant) and isinstance(path_node, ast.Constant):
                    method = str(method_node.value)
                    path = str(path_node.value)
                    if method in MUTATION_METHODS and path.startswith("/api/admin"):
                        cases.add((method, path))
    return cases


def main() -> int:
    route_cases = _admin_role_protected_mutation_routes()
    matrix_cases = _matrix_endpoint_cases()

    route_count = len(route_cases)
    matrix_count = len(matrix_cases)
    ratio = (matrix_count / route_count) if route_count else 1.0

    print(f"mutation_route_count={route_count}")
    print(f"matrix_case_count={matrix_count}")
    print(f"matrix_coverage_ratio={ratio:.3f}")

    if matrix_count < MIN_MATRIX_CASES:
        print(
            f"FAIL: matrix cases too low (got {matrix_count}, need >= {MIN_MATRIX_CASES})"
        )
        return 1

    if route_count and ratio < MIN_COVERAGE_RATIO:
        print(
            f"FAIL: matrix coverage ratio too low (got {ratio:.3f}, need >= {MIN_COVERAGE_RATIO:.3f})"
        )
        return 1

    print("PASS: mutation route-count vs matrix coverage gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
