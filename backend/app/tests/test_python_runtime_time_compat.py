from __future__ import annotations

from pathlib import Path


def test_no_runtime_datetime_utcnow_calls() -> None:
    root = Path(__file__).resolve().parents[2] / "app"
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        if "/tests/" in path.as_posix():
            continue
        text = path.read_text(encoding="utf-8")
        if "datetime.utcnow(" in text:
            offenders.append(path.as_posix())

    assert offenders == []
