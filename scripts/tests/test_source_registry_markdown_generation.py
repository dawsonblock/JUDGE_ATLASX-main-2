from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_release_gate_module(repo_root: Path):
    module_name = "release_gate_module"
    module_path = repo_root / "scripts" / "release_gate.py"
    spec = importlib.util.spec_from_file_location(
        module_name,
        str(module_path),
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_truth_table_module(repo_root: Path):
    module_name = "source_registry_truth_table_module"
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


def test_source_registry_markdown_generation_uses_current_schema(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    out_dir = repo_root / "artifacts" / "proof" / "current"
    docs_dir = repo_root / "docs"
    out_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)

    release_gate = _load_release_gate_module(
        Path(__file__).resolve().parents[2]
    )

    payload = {
        "timestamp_utc": "2026-05-16T00:00:00Z",
        "commit_hash": "abc123",
    }
    source_registry_summary = {
        "summary": {
            "total_sources": 26,
            "machine_ingest_sources": 7,
            "runnable_now": 1,
            "enable_ready": 5,
            "deprecated": 3,
        },
        "sources": [
            {
                "source_key": "justice_canada_laws_xml",
                "source_name": "Justice Canada Laws XML",
                "jurisdiction": "Canada",
                "source_class": "machine_ingest",
                "source_type": "legislation",
                "lifecycle_state": "active",
                "automation_status": "machine_ready_enabled",
                "adapter_state": "found",
                "parser": "justice_canada_xml",
                "adapter_exists": True,
                "runnable_now": True,
                "enable_ready": False,
                "blockers": [],
                "public_visibility_policy": {"requires_manual_review": True},
            },
            {
                "source_key": "scc_decisions",
                "source_name": "Supreme Court of Canada",
                "jurisdiction": "Canada",
                "source_class": "machine_ingest",
                "source_type": "court_record",
                "lifecycle_state": "active",
                "automation_status": "machine_ready_disabled",
                "adapter_state": "found",
                "parser": "scc_lexum_api",
                "adapter_exists": True,
                "runnable_now": False,
                "enable_ready": True,
                "blockers": ["source_disabled"],
                "public_visibility_policy": {"requires_manual_review": True},
            },
            {
                "source_key": "federal_court_canada",
                "source_name": "Federal Court of Canada",
                "jurisdiction": "Canada",
                "source_class": "machine_ingest",
                "source_type": "court_record",
                "lifecycle_state": "active",
                "automation_status": "machine_ready_disabled",
                "adapter_state": "found",
                "parser": "federal_court_html",
                "adapter_exists": True,
                "runnable_now": False,
                "enable_ready": True,
                "blockers": ["source_disabled"],
                "public_visibility_policy": {"requires_manual_review": True},
            },
            {
                "source_key": "sk_courts_qb_decisions",
                "source_name": "Saskatchewan QB",
                "jurisdiction": "CA-SK",
                "source_class": "machine_ingest",
                "source_type": "court_record",
                "lifecycle_state": "active",
                "automation_status": "machine_ready_disabled",
                "adapter_state": "found",
                "parser": "sk_qb_html",
                "adapter_exists": True,
                "runnable_now": False,
                "enable_ready": True,
                "blockers": ["source_disabled"],
                "public_visibility_policy": {"requires_manual_review": True},
            },
            {
                "source_key": "sk_courts_ca_decisions",
                "source_name": "Saskatchewan CA",
                "jurisdiction": "CA-SK",
                "source_class": "machine_ingest",
                "source_type": "court_record",
                "lifecycle_state": "active",
                "automation_status": "machine_ready_disabled",
                "adapter_state": "found",
                "parser": "sk_ca_html",
                "adapter_exists": True,
                "runnable_now": False,
                "enable_ready": True,
                "blockers": ["source_disabled"],
                "public_visibility_policy": {"requires_manual_review": True},
            },
            {
                "source_key": "sk_legislature_hansard",
                "source_name": "Saskatchewan Hansard",
                "jurisdiction": "CA-SK",
                "source_class": "machine_ingest",
                "source_type": "legislative_record",
                "lifecycle_state": "active",
                "automation_status": "machine_ready_disabled",
                "adapter_state": "found",
                "parser": "sk_hansard_html",
                "adapter_exists": True,
                "runnable_now": False,
                "enable_ready": True,
                "blockers": ["source_disabled"],
                "public_visibility_policy": {"requires_manual_review": True},
            },
        ],
    }

    release_gate._write_source_registry_status_md(
        repo_root,
        out_dir,
        payload,
        source_registry_summary,
    )

    text = (out_dir / "SOURCE_REGISTRY_STATUS.md").read_text(encoding="utf-8")

    assert "unknown" not in text.lower()
    assert "- total_sources: 26" in text
    assert "- runnable_now: 1" in text
    assert "- enable_ready: 5" in text
    assert "| justice_canada_laws_xml |" in text
    assert "| justice_canada_laws_xml | Justice Canada Laws XML" in text

    parsed_rows: list[list[str]] = []
    for line in text.splitlines():
        if not line.startswith("| "):
            continue
        if line.startswith("|---"):
            continue
        cols = [item.strip() for item in line.strip().strip("|").split("|")]
        if cols and cols[0] != "source key":
            parsed_rows.append(cols)

    enable_ready_sources = {
        row[0] for row in parsed_rows if len(row) > 10 and row[10] == "yes"
    }
    assert enable_ready_sources == {
        "scc_decisions",
        "federal_court_canada",
        "sk_courts_qb_decisions",
        "sk_courts_ca_decisions",
        "sk_legislature_hansard",
    }


def test_truth_table_marks_stub_and_portal_sources_non_runnable() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    truth_table = _load_truth_table_module(repo_root)

    sources = [
        {
            "source_key": "sk_justice_ministry",
            "source_class": "disabled_stub",
            "lifecycle_state": "disabled_stub",
            "automation_status": "adapter_missing",
            "parser": "crawlee_gov_news",
            "parser_version": None,
            "base_url": "https://www.saskatchewan.ca",
        },
        {
            "source_key": "rcmp_sk_news",
            "source_class": "disabled_stub",
            "lifecycle_state": "disabled_stub",
            "automation_status": "adapter_missing",
            "parser": "crawlee_police_release",
            "parser_version": None,
            "base_url": "https://www.rcmp-grc.gc.ca",
        },
        {
            "source_key": "statscan_crime_tables",
            "source_class": "portal_reference",
            "lifecycle_state": "portal_reference",
            "automation_status": "adapter_missing",
            "parser": "statscan_table",
            "parser_version": None,
            "base_url": "https://www150.statcan.gc.ca",
        },
    ]
    lifecycle_by_key = {s["source_key"]: s["lifecycle_state"] for s in sources}

    sk_justice = truth_table.compute_lifecycle_status(
        sources[0],
        lifecycle_by_key,
        adapter_exists=False,
    )
    assert sk_justice["runnable_now"] is False
    assert sk_justice["enable_ready"] is False
    assert "lifecycle_state=disabled_stub" in sk_justice["blockers"]
    assert "automation_status=adapter_missing" in sk_justice["blockers"]
    assert "adapter_missing" in sk_justice["blockers"]

    rcmp = truth_table.compute_lifecycle_status(
        sources[1],
        lifecycle_by_key,
        adapter_exists=False,
    )
    assert rcmp["runnable_now"] is False
    assert rcmp["enable_ready"] is False
    assert "lifecycle_state=disabled_stub" in rcmp["blockers"]
    assert "automation_status=adapter_missing" in rcmp["blockers"]
    assert "adapter_missing" in rcmp["blockers"]

    statscan = truth_table.compute_lifecycle_status(
        sources[2],
        lifecycle_by_key,
        adapter_exists=True,
    )
    assert statscan["runnable_now"] is False
    assert statscan["enable_ready"] is False
    assert "lifecycle_state=portal_reference" in statscan["blockers"]
    assert "automation_status=adapter_missing" in statscan["blockers"]
