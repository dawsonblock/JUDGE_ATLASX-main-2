"""CLI runtime tests for verify_audit_chain.py."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.audit.chain_digest import GENESIS_HASH, row_digest
from app.auth import admin as auth_admin
from app.auth.actor import AdminActor
from app.db.session import Base
from app.models.entities import AuditLog


def _make_session_factory(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'audit_cli.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _seed_chain(session_factory, monkeypatch, actions: list[str]) -> None:
    monkeypatch.setattr(auth_admin, "SessionLocal", session_factory)
    actor = AdminActor(
        actor_id="admin-123",
        actor_type="jwt",
        role="admin",
        auth_method="jwt",
    )
    for idx, action in enumerate(actions, start=1):
        auth_admin.log_mutation(
            action=action,
            entity_type="audit_test",
            entity_id=str(idx),
            payload={"step": idx},
            actor=actor,
        )


def _run_cli(db_path: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["JTA_DATABASE_URL"] = f"sqlite:///{db_path}"
    repo_root = Path(__file__).resolve().parents[3]
    return subprocess.run(
        [sys.executable, "-m", "backend.tools.verify_audit_chain"],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_verify_audit_chain_cli_passes_on_seeded_chain(tmp_path, monkeypatch):
    session_factory = _make_session_factory(tmp_path)
    _seed_chain(
        session_factory,
        monkeypatch,
        ["audit.seed.one", "audit.seed.two", "audit.seed.three"],
    )

    result = _run_cli(tmp_path / "audit_cli.db")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "entries_checked=3" in result.stdout
    assert "RESULT: PASS" in result.stdout


def test_verify_audit_chain_cli_fails_on_tampered_payload(tmp_path, monkeypatch):
    session_factory = _make_session_factory(tmp_path)
    _seed_chain(
        session_factory,
        monkeypatch,
        ["audit.seed.one", "audit.seed.two", "audit.seed.three"],
    )

    with session_factory() as db:
        row = db.query(AuditLog).order_by(AuditLog.id.asc()).offset(1).first()
        assert row is not None
        row.payload = {"tampered": True}
        row.entry_hash = row_digest(row, row.previous_entry_hash or GENESIS_HASH)
        # Break the chain by changing the stored previous hash on the middle row.
        row.previous_entry_hash = "broken-previous-hash"
        db.commit()

    result = _run_cli(tmp_path / "audit_cli.db")
    assert result.returncode != 0
    assert "violations=" in result.stdout
