from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "prove_justice_canada_ingestion.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("prove_justice_canada_ingestion", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_report_contains_registry_truth() -> None:
    module = _load_module()

    report = module.build_report(live_mode=False)

    assert "source_key: justice_canada_laws_xml" in report
    assert "source is machine_ingest: PASS" in report
    assert "records private/pending by default: PASS" in report
