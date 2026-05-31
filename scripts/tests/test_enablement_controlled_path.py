from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_truth_table_module(repo_root: Path):
    module_name = "source_registry_truth_table_controlled_path"
    module_path = (
        repo_root / "scripts" / "generate_source_registry_truth_table.py"
    )
    spec = importlib.util.spec_from_file_location(
        module_name,
        str(module_path),
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_canadian_enablement_controlled_path_lock() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    truth_table = _load_truth_table_module(repo_root)

    sources = truth_table.load_sources_yaml()
    truth = truth_table.generate_truth_table_json(sources)
    rows = truth["sources"]

    enable_ready_keys = {
        row["source_key"]
        for row in rows
        if row.get("enable_ready") is True
    }
    assert enable_ready_keys == {
        "scc_decisions",
        "federal_court_canada",
        "sk_courts_qb_decisions",
        "sk_courts_ca_decisions",
        "sk_legislature_hansard",
    }

    for row in rows:
        if row["source_key"] not in enable_ready_keys:
            continue
        assert row["source_class"] == "machine_ingest"
        assert row["lifecycle_state"] == "runnable_disabled"
        assert row["automation_status"] == "machine_ready_disabled"
        assert row["runnable_now"] is False
        assert "Canada" in (row.get("jurisdiction") or "")

    blocked_stub_keys = {"sk_justice_ministry", "rcmp_sk_news"}
    for row in rows:
        if row["source_key"] in blocked_stub_keys:
            assert row["enable_ready"] is False
            blockers = set(row.get("blockers") or [])
            assert "lifecycle_state=disabled_stub" in blockers
            assert "automation_status=adapter_missing" in blockers
