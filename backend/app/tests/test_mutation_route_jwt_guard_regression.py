from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


MUTATION_GUARD_TARGETS: list[tuple[str, str]] = [
    (
        "backend/app/api/routes/admin_review.py",
        "def retract_legal_source(",
    ),
    (
        "backend/app/api/routes/ai_correctness.py",
        "def run_incident_check(",
    ),
    (
        "backend/app/api/routes/ai_correctness.py",
        "def run_event_check(",
    ),
    (
        "backend/app/api/routes/ai_correctness.py",
        "def verify_source_endpoint(",
    ),
    (
        "backend/app/api/routes/evidence.py",
        "def create_evidence(",
    ),
    (
        "backend/app/api/routes/evidence.py",
        "def verify_evidence(",
    ),
    (
        "backend/app/api/routes/evidence.py",
        "def unverify_evidence(",
    ),
    (
        "backend/app/api/routes/graph.py",
        "def create_edge(",
    ),
]


HELPER_ENFORCED_DEPENDENCIES = (
    "Depends(require_admin_actor)",
    "Depends(require_ai_review_actor)",
    "Depends(require_source_admin_actor)",
    "Depends(require_reviewer_actor)",
)


def _function_block(source: str, function_signature: str) -> str:
    start = source.find(function_signature)
    assert start != -1, f"Function signature not found: {function_signature}"
    next_def = source.find("\ndef ", start + len(function_signature))
    if next_def == -1:
        return source[start:]
    return source[start:next_def]


def test_mutation_routes_enforce_jwt_authority() -> None:
    missing: list[str] = []

    for rel_path, function_signature in MUTATION_GUARD_TARGETS:
        file_path = REPO_ROOT / rel_path
        source = file_path.read_text(encoding="utf-8")
        block = _function_block(source, function_signature)
        has_direct_guard = "enforce_jwt_mutation_authority(" in block
        has_helper_guard = any(
            dep in block for dep in HELPER_ENFORCED_DEPENDENCIES
        )
        if not (has_direct_guard or has_helper_guard):
            missing.append(f"{rel_path}::{function_signature}")

    assert not missing, "Missing JWT mutation guard: " + ", ".join(missing)
