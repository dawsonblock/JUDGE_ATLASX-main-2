#!/usr/bin/env python3
"""Verify map route behavior and reviewed-only/public-only query guards.

Checks:
    1. ``/map`` route exists with a concrete page implementation
    2. ``/map`` page is not a placeholder stub
    3. ``/map`` page does not reference legacy ``/map-v2``
    4. backend map query path enforces reviewed/public filters for returned records

Exits 0 on success, 1 on failure. Writes a summary to stdout.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_APP = REPO_ROOT / "frontend" / "app"
BACKEND_APP = REPO_ROOT / "backend" / "app"
BACKEND_VENV_PYTHON = REPO_ROOT / "backend" / ".venv" / "bin" / "python"

REQUIRED_ROUTES = ["map"]

# Tokens that indicate a stub/placeholder page that has not been implemented
PLACEHOLDER_TOKENS = [
    "TODO",
    "Coming soon",
    "Placeholder",
    "under construction",
    "not implemented",
]


def _find_page_file(route_dir: Path) -> Path | None:
    for name in ("page.tsx", "page.jsx", "page.ts", "page.js"):
        candidate = route_dir / name
        if candidate.is_file():
            return candidate
    return None


def _contains_any(content: str, patterns: list[str]) -> bool:
    content_lower = content.lower()
    return any(p.lower() in content_lower for p in patterns)


def main() -> int:
    findings: list[str] = []

    for route in REQUIRED_ROUTES:
        route_dir = FRONTEND_APP / route
        if not route_dir.is_dir():
            findings.append(f"MISSING route directory: frontend/app/{route}/")
            continue

        page_file = _find_page_file(route_dir)
        if page_file is None:
            findings.append(
                f"MISSING page file in frontend/app/{route}/ (expected page.tsx)"
            )
            continue

        content = page_file.read_text(encoding="utf-8")
        if len(content.strip()) < 10:
            findings.append(f"EMPTY page: {page_file.relative_to(REPO_ROOT)}")
            continue

        for token in PLACEHOLDER_TOKENS:
            if token.lower() in content.lower():
                findings.append(
                    f"PLACEHOLDER in {page_file.relative_to(REPO_ROOT)}: found {token!r}"
                )
                break

    # Verify /map canonical behavior.
    map_page = _find_page_file(FRONTEND_APP / "map")
    if map_page is None:
        findings.append("MISSING /map page file for canonical route check")
    else:
        map_text = map_page.read_text(encoding="utf-8")
        if "MapWorkspace" not in map_text:
            findings.append("/map page does not render MapWorkspace")
        if _contains_any(map_text, ["/map-v2", "/map/v2"]):
            findings.append("/map page still references legacy /map-v2")

    # Verify reviewed/public-only filters in backend map query path.
    map_route_file = BACKEND_APP / "api" / "routes" / "map.py"
    public_serializer_file = BACKEND_APP / "serializers" / "public.py"

    if not map_route_file.is_file():
        findings.append("MISSING backend map route file: backend/app/api/routes/map.py")
    else:
        map_route_text = map_route_file.read_text(encoding="utf-8")
        if "CrimeIncident.is_public.is_(True)" not in map_route_text:
            findings.append(
                "backend map route missing CrimeIncident.is_public public-only guard"
            )
        if (
            "CrimeIncident.review_status.in_(PUBLIC_REVIEW_STATUSES)"
            not in map_route_text
        ):
            findings.append(
                "backend map route missing CrimeIncident reviewed-status guard"
            )
        if "filtered_events_query(" not in map_route_text:
            findings.append("backend map route missing filtered_events_query() call")

    if not public_serializer_file.is_file():
        findings.append(
            "MISSING event serializer file: backend/app/serializers/public.py"
        )
    else:
        serializer_text = public_serializer_file.read_text(encoding="utf-8")
        if "Event.public_visibility.is_(True)" not in serializer_text:
            findings.append(
                "event serializer missing Event.public_visibility public-only guard"
            )
        if "Event.review_status.in_(PUBLIC_REVIEW_STATUSES)" not in serializer_text:
            findings.append("event serializer missing Event reviewed-status guard")

    map_proof_test = (
        REPO_ROOT / "backend" / "app" / "tests" / "test_public_map_reviewed_only.py"
    )
    if not map_proof_test.is_file():
        findings.append(
            "MISSING map reviewed-only proof test: backend/app/tests/test_public_map_reviewed_only.py"
        )
    else:
        proc = subprocess.run(
            [
                (
                    str(BACKEND_VENV_PYTHON)
                    if BACKEND_VENV_PYTHON.exists()
                    else sys.executable
                ),
                "-m",
                "pytest",
                str(map_proof_test),
                "-q",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            findings.append("map reviewed-only proof tests failed")
            if proc.stdout.strip():
                findings.append(f"pytest_stdout={proc.stdout.strip().splitlines()[-1]}")
            if proc.stderr.strip():
                findings.append(f"pytest_stderr={proc.stderr.strip().splitlines()[-1]}")

    if findings:
        print("RESULT: FAIL")
        for f in findings:
            print(f"  {f}")
        return 1

    print("RESULT: PASS")
    for route in REQUIRED_ROUTES:
        page_file = _find_page_file(FRONTEND_APP / route)
        size = page_file.stat().st_size if page_file else 0
        print(f"  OK frontend/app/{route}/ ({size} bytes)")
    print("  OK /map canonical route verified")
    print("  OK backend reviewed/public filters verified")
    print("  OK map reviewed-only proof tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
