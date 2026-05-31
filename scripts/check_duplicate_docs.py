#!/usr/bin/env python3
"""CI check: fail if duplicate canonical docs are found.

Scans docs/ for multiple files that could canonically represent the same
topic (status, proof, architecture, release-blockers). Only one canonical
file per topic is permitted outside of docs/archive/.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_ROOT = REPO_ROOT / "docs"

# Patterns for topics that must have exactly one canonical doc.
# Each entry: (topic_label, list of filename stems that are canonical for that topic)
CANONICAL_TOPICS: list[tuple[str, list[str]]] = [
    ("current_status", ["CURRENT_STATUS", "CURRENT_ALPHA_STATUS"]),
    ("proof", ["CURRENT_PROOF", "PROOF_POLICY", "PROOF_MANIFEST"]),
    ("release_blockers", ["RELEASE_BLOCKERS"]),
    ("architecture", ["ARCHITECTURE"]),
    ("source_registry", ["SOURCE_REGISTRY", "SOURCE_REGISTRY_STATUS"]),
    ("security_model", ["SECURITY_MODEL"]),
    ("evidence_model", ["EVIDENCE_MODEL"]),
    ("legal_risk", ["LEGAL_RISK_BOUNDARIES"]),
]

# Directories that are explicitly allowed to hold archived duplicates.
ARCHIVE_DIRS = {
    "archive",
    "docs/archive",
    "history",
    "docs/history",
}


def _is_archived(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    return bool(parts & ARCHIVE_DIRS)


def main() -> int:
    violations: list[str] = []

    for topic, stems in CANONICAL_TOPICS:
        for stem in stems:
            stem_matches: list[Path] = []
            for md_file in DOCS_ROOT.rglob(f"{stem}.md"):
                if not _is_archived(md_file):
                    stem_matches.append(md_file)

            if len(stem_matches) > 1:
                for f in stem_matches[1:]:
                    violations.append(
                        f"duplicate canonical doc [{topic}/{stem}]: {f.relative_to(REPO_ROOT)}"
                    )

    if violations:
        print("check_duplicate_docs: FAIL")
        for v in violations:
            print(f"  {v}")
        return 1

    total_checked = sum(len(stems) for _, stems in CANONICAL_TOPICS)
    print(f"check_duplicate_docs: PASS (checked {total_checked} canonical doc patterns)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
