from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_gate() -> dict:
    gate_path = ROOT / "artifacts" / "proof" / "current" / "release_gate.json"
    assert gate_path.exists(), f"Missing canonical gate file: {gate_path}"
    return json.loads(gate_path.read_text(encoding="utf-8"))


def _load_doc(path: Path) -> str:
    assert path.exists(), f"Missing proof document: {path}"
    return path.read_text(encoding="utf-8", errors="replace").lower()


def test_proof_docs_match_release_gate() -> None:
    gate = _load_gate()
    gate_passed = bool(gate.get("alpha_gate_passed"))

    docs = [
        ROOT / "CURRENT_PROOF.md",
        ROOT / "artifacts" / "proof" / "current" / "release_readiness.md",
        ROOT / "artifacts" / "proof" / "current" / "FIX_VERIFICATION_REPORT.md",
    ]

    pass_phrases = [
        "alpha-proof-pass",
        "alpha_gate_passed: true",
        "remaining blockers: none",
        "release_candidate: true",
    ]
    blocked_phrases = [
        "blocked",
        "alpha_gate_passed: false",
        "release_candidate: false",
    ]

    for path in docs:
        text = _load_doc(path)
        if not gate_passed:
            for phrase in pass_phrases:
                assert phrase not in text, (
                    f"{path} claims pass while release_gate.json is blocked"
                )
            assert any(phrase in text for phrase in blocked_phrases), (
                f"{path} does not clearly reflect blocked gate"
            )
