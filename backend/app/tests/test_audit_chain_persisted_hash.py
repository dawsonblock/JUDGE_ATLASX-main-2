"""Integration tests for persisted audit-chain hashes."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import admin as auth_admin
from app.auth.actor import AdminActor
from app.db.session import Base
from app.models.entities import AuditLog


def _make_temp_session_factory(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'audit_chain.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def test_log_mutation_persists_entry_and_previous_hash(tmp_path, monkeypatch):
    session_factory = _make_temp_session_factory(tmp_path)
    monkeypatch.setattr(auth_admin, "SessionLocal", session_factory)

    actor = AdminActor(
        actor_id="admin-123",
        actor_type="jwt",
        role="admin",
        auth_method="jwt",
    )

    auth_admin.log_mutation(
        action="audit.persisted.test",
        entity_type="audit_test",
        entity_id="1",
        payload={"hello": "world"},
        actor=actor,
        request_id="req-1",
    )

    with session_factory() as db:
        rows = db.query(AuditLog).order_by(AuditLog.id.asc()).all()

    assert len(rows) == 1
    row = rows[0]
    assert row.previous_entry_hash == "GENESIS"
    assert row.entry_hash is not None
    assert len(row.entry_hash) == 64


def test_second_log_mutation_links_previous_entry_hash(tmp_path, monkeypatch):
    session_factory = _make_temp_session_factory(tmp_path)
    monkeypatch.setattr(auth_admin, "SessionLocal", session_factory)

    actor = AdminActor(
        actor_id="admin-123",
        actor_type="jwt",
        role="admin",
        auth_method="jwt",
    )

    auth_admin.log_mutation(
        action="audit.persisted.first",
        entity_type="audit_test",
        entity_id="1",
        payload={"step": 1},
        actor=actor,
    )
    auth_admin.log_mutation(
        action="audit.persisted.second",
        entity_type="audit_test",
        entity_id="2",
        payload={"step": 2},
        actor=actor,
    )

    with session_factory() as db:
        rows = db.query(AuditLog).order_by(AuditLog.id.asc()).all()

    assert len(rows) == 2
    first, second = rows
    assert first.entry_hash is not None
    assert second.previous_entry_hash == first.entry_hash
    assert second.entry_hash is not None
    assert first.entry_hash != second.entry_hash