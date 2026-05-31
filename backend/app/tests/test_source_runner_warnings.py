from __future__ import annotations

from app.ingestion.source_runner import RunPersistSummary, _summarize_warning_code


def test_warning_summary_dedupes_warning_codes() -> None:
    summary = RunPersistSummary()

    _summarize_warning_code(summary, "duplicate_record_skipped")
    _summarize_warning_code(summary, "duplicate_record_skipped")

    assert summary.warnings == ["duplicate_record_skipped"]
