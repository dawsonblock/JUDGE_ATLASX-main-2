from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "report_stub_adapters.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("report_stub_adapters", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_stub_findings_not_runnable() -> None:
    module = _load_module()

    findings = module._find_stubs()

    assert findings
    assert all(finding["runnable"] is False for finding in findings)
    assert any(
        finding["reason"] in {"not_implemented_stub", "adapter_missing", "class_disabled_stub"}
        for finding in findings
    )
