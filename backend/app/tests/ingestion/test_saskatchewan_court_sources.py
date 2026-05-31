"""Saskatchewan court source fixture contracts at ingestion-matrix path."""

from __future__ import annotations

import json
from pathlib import Path


def test_saskatchewan_court_fixture_files_exist_and_shape() -> None:
    fixture_dir = Path(__file__).resolve().parents[1] / "fixtures"
    qb = fixture_dir / "sk_qb_decision_sample.json"
    ca = fixture_dir / "sk_ca_decision_sample.json"

    assert qb.exists()
    assert ca.exists()

    for file_path in (qb, ca):
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        assert "case_name" in payload
        assert "court" in payload
        assert "decision_date" in payload
        assert "source_url" in payload
