#!/usr/bin/env python3
"""CI guard: validate Dockerfile COPY/ADD local source paths exist.

The checker scans Dockerfile* files under the repository root and fails if any
local COPY/ADD source path does not resolve on disk. It ignores:
- COPY --from=<stage> ... (stage/file-system copies)
- Remote URL sources
- Unresolved variable sources (for example, $SRC or ${SRC})

To reduce false positives with different build contexts, each source is
considered valid if it exists relative to either the repository root or the
Dockerfile's directory.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

IGNORE_PREFIXES = {
    ".git/",
    ".venv/",
    "node_modules/",
    "frontend/node_modules/",
    "backend/.venv/",
    "artifacts/proof/current/",
    "artifacts/proof/history/",
}


@dataclass
class Violation:
    dockerfile: Path
    line_number: int
    source: str
    reason: str


def _normalize(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _iter_dockerfiles(root: Path) -> list[Path]:
    files: list[Path] = []
    for candidate in root.rglob("Dockerfile*"):
        if not candidate.is_file():
            continue
        rel = _normalize(candidate, root)
        if any(rel.startswith(prefix) for prefix in IGNORE_PREFIXES):
            continue
        files.append(candidate)
    return sorted(files)


def _logical_lines(text: str) -> list[tuple[int, str]]:
    lines = text.splitlines()
    combined: list[tuple[int, str]] = []
    buffer: list[str] = []
    start_line = 1

    for idx, raw_line in enumerate(lines, start=1):
        if not buffer:
            start_line = idx
        stripped = raw_line.strip()
        if not stripped and not buffer:
            continue

        if stripped.endswith("\\"):
            buffer.append(stripped[:-1].rstrip())
            continue

        if buffer:
            buffer.append(stripped)
            combined.append((start_line, " ".join(part for part in buffer if part)))
            buffer = []
            continue

        combined.append((idx, stripped))

    if buffer:
        combined.append((start_line, " ".join(part for part in buffer if part)))
    return combined


def _is_remote_source(token: str) -> bool:
    lowered = token.lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


def _contains_unresolved_var(token: str) -> bool:
    return "$" in token


def _extract_sources_from_instruction(instruction: str) -> list[str] | None:
    match = re.match(r"^(copy|add)\s+(.*)$", instruction, flags=re.IGNORECASE)
    if not match:
        return None
    payload = match.group(2).strip()
    if not payload:
        return []

    # JSON-array form: COPY ["src", "dest"]
    if payload.startswith("["):
        try:
            parts = json.loads(payload)
        except json.JSONDecodeError:
            return []
        if not isinstance(parts, list) or len(parts) < 2:
            return []
        srcs = [str(item) for item in parts[:-1]]
        return srcs

    try:
        tokens = shlex.split(payload)
    except ValueError:
        return []

    filtered: list[str] = []
    idx = 0
    while idx < len(tokens):
        token = tokens[idx]
        if token.startswith("--from=") or token == "--from":
            # Stage copy; ignore whole instruction for local path checks.
            return []
        if token.startswith("--"):
            # Flags like --link are boolean and do not consume the next token.
            if token == "--link" or token.startswith("--link="):
                idx += 1
                continue
            # Handle flags whose value may be in the next token.
            if token in {"--chown", "--chmod", "--exclude", "--parents"}:
                idx += 2
                continue
            # Handle inline key=value flags.
            if any(
                token.startswith(prefix)
                for prefix in (
                    "--chown=",
                    "--chmod=",
                    "--exclude=",
                    "--parents=",
                )
            ):
                idx += 1
                continue
            idx += 1
            continue
        filtered.extend(tokens[idx:])
        break

    if len(filtered) < 2:
        return []
    return filtered[:-1]


def _source_exists(root: Path, dockerfile: Path, source: str) -> bool:
    source_path = Path(source)

    candidates = [root / source_path, dockerfile.parent / source_path]
    for candidate in candidates:
        if any(ch in source for ch in "*?[]"):
            if list(candidate.parent.glob(candidate.name)):
                return True
            continue
        if candidate.exists():
            return True
    return False


def validate_dockerfile(root: Path, dockerfile: Path) -> list[Violation]:
    text = dockerfile.read_text(encoding="utf-8")
    violations: list[Violation] = []

    for line_number, line in _logical_lines(text):
        if not line or line.startswith("#"):
            continue
        sources = _extract_sources_from_instruction(line)
        if sources is None:
            continue
        for source in sources:
            if _is_remote_source(source) or _contains_unresolved_var(source):
                continue
            if not _source_exists(root, dockerfile, source):
                violations.append(
                    Violation(
                        dockerfile=dockerfile,
                        line_number=line_number,
                        source=source,
                        reason="source path does not exist",
                    )
                )
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root path (default: current directory)",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"ERROR: root does not exist: {root}", file=sys.stderr)
        return 2

    dockerfiles = _iter_dockerfiles(root)
    if not dockerfiles:
        print("check_dockerfile_copy_paths: OK — no Dockerfile* files found.")
        return 0

    violations: list[Violation] = []
    for dockerfile in dockerfiles:
        violations.extend(validate_dockerfile(root, dockerfile))

    if violations:
        print("check_dockerfile_copy_paths: FAILED — missing COPY/ADD sources detected:")
        for violation in violations:
            rel = _normalize(violation.dockerfile, root)
            print(
                f"  {rel}:{violation.line_number}: {violation.source} ({violation.reason})"
            )
        return 1

    print(
        "check_dockerfile_copy_paths: OK — all local COPY/ADD sources resolve "
        f"across {len(dockerfiles)} Dockerfile(s)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
