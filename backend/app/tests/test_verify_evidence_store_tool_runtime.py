"""CLI runtime tests for verify_evidence_store.py."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.entities import SourceSnapshot
from app.services.snapshot_writer import write_snapshot


def _make_session_factory(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'evidence_cli.db'}")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _run_cli(db_path: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["JTA_DATABASE_URL"] = f"sqlite:///{db_path}"
    repo_root = Path(__file__).resolve().parents[3]
    return subprocess.run(
        [sys.executable, "-m", "backend.tools.verify_evidence_store"],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_verify_evidence_store_cli_passes_on_seeded_snapshots(tmp_path):
    session_factory = _make_session_factory(tmp_path)
    with session_factory() as db:
        write_snapshot(
            db=db,
            source_url="https://example.test/source-a",
            fetched_at=datetime.now(timezone.utc),
            content=b"first evidence snapshot",
            source_key="source-a",
        )
        write_snapshot(
            db=db,
            source_url="https://example.test/source-b",
            fetched_at=datetime.now(timezone.utc),
            content=b"second evidence snapshot",
            source_key="source-b",
        )
        db.commit()

    result = _run_cli(tmp_path / "evidence_cli.db")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "snapshots_checked=2" in result.stdout
    assert "verified_snapshots=2" in result.stdout
    assert "RESULT: PASS" in result.stdout


def test_verify_evidence_store_cli_fails_on_corrupted_snapshot(tmp_path):
    session_factory = _make_session_factory(tmp_path)
    with session_factory() as db:
        snap = write_snapshot(
            db=db,
            source_url="https://example.test/source-a",
            fetched_at=datetime.now(timezone.utc),
            content=b"first evidence snapshot",
            source_key="source-a",
        )
        db.commit()

    # Use raw SQL to bypass ORM immutability event listener on content_hash
    engine = create_engine(f"sqlite:///{tmp_path / 'evidence_cli.db'}")
    with engine.connect() as conn:
        from sqlalchemy import text
        conn.execute(
            text("UPDATE source_snapshots SET content_hash = :bad WHERE id = 1"),
            {"bad": "0" * 64},
        )
        conn.commit()

    result = _run_cli(tmp_path / "evidence_cli.db")
    assert result.returncode != 0
    assert "integrity_failures=1" in result.stdout
    assert "RESULT: FAIL" in result.stdout
