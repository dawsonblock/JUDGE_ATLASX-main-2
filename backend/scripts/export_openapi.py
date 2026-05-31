#!/usr/bin/env python3
"""Export the FastAPI OpenAPI schema to stdout as JSON.

Usage:
    python backend/scripts/export_openapi.py > frontend/lib/api/openapi.json

Then generate TypeScript types:
    npx openapi-typescript frontend/lib/api/openapi.json \
        -o frontend/lib/api/types.ts

This ensures the frontend always uses types derived from the actual backend
schema rather than hand-written assumptions.

Environment variables (optional):
    JTA_DATABASE_URL  — Override the database URL (defaults to sqlite:///./dev.db)
    JTA_APP_ENV       — Override the environment (defaults to development)
"""

from __future__ import annotations

import json
import os
import sys

# Set minimal environment for schema export (no real DB needed)
os.environ.setdefault("JTA_APP_ENV", "development")
os.environ.setdefault("JTA_DATABASE_URL", "sqlite:///./dev.db")
os.environ.setdefault("JTA_ADMIN_TOKEN", "export-schema-token")

# Add the backend directory to the path so 'app' is importable
_here = os.path.dirname(os.path.abspath(__file__))
_backend = os.path.dirname(_here)
if _backend not in sys.path:
    sys.path.insert(0, _backend)

from app.main import app  # noqa: E402


def main() -> None:
    schema = app.openapi()
    json.dump(schema, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
