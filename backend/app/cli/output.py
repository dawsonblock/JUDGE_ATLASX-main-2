"""Standard JSON envelope for judgectl output."""

from __future__ import annotations

import json
import sys
from typing import Any


def emit(
    data: Any,
    *,
    ok: bool = True,
    command: str = "",
    as_json: bool = False,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> None:
    """Print result to stdout.

    In JSON mode: always prints the full envelope.
    In human mode: prints a simple text or table.
    """
    if as_json:
        envelope = {
            "ok": ok,
            "command": command,
            "data": data,
            "warnings": warnings or [],
            "errors": errors or [],
        }
        print(json.dumps(envelope, default=str))
    else:
        if isinstance(data, list):
            for item in data:
                print(item)
        elif isinstance(data, dict):
            for k, v in data.items():
                print(f"{k}: {v}")
        else:
            print(data)


def emit_error(
    message: str,
    *,
    command: str = "",
    error_code: str = "ERROR",
    next_action: str = "",
    as_json: bool = False,
    **extra: object,
) -> None:
    """Print error to stderr (human mode) or stdout (JSON mode)."""
    if as_json:
        envelope: dict[str, Any] = {
            "ok": False,
            "command": command,
            "error_code": error_code,
            "message": message,
            "next_action": next_action,
        }
        envelope.update(extra)
        print(json.dumps(envelope, default=str))
    else:
        print(f"ERROR [{error_code}]: {message}", file=sys.stderr)
        if next_action:
            print(f"  \u2192 {next_action}", file=sys.stderr)
