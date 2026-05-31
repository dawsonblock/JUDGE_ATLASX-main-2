from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.audit.append_log import append_audit_entry
from app.audit.integrity_chain import verify_chain
from app.db.session import Base
from app.models.entities import AuditLog


class _FakeDialect:
    name = "postgresql"


class _FakeBind:
    dialect = _FakeDialect()


class _FakeQuery:
    def order_by(self, *_args, **_kwargs):
        return self

    def first(self):
        return None


class _FakeSession:
    def __init__(self) -> None:
        self.executed: list[tuple[str, dict]] = []

    def get_bind(self):
        return _FakeBind()

    def execute(self, statement, params):
        self.executed.append((str(statement), params))

    def query(self, *_args, **_kwargs):
        return _FakeQuery()

    def add(self, _entry):
        return None

    def flush(self):
        return None


def _make_session_factory(tmp_path: Path):
    db_path = tmp_path / "audit_chain_concurrency.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def test_append_audit_entry_acquires_pg_advisory_lock_before_chain_read() -> None:
    db = _FakeSession()

    append_audit_entry(
        db,
        action="audit.lock.test",
        entity_type="audit",
        entity_id="1",
        actor_id="admin",
        actor_role="admin",
        actor_auth_method="jwt",
        payload={"k": "v"},
    )

    assert db.executed, "expected advisory lock SQL execution for PostgreSQL"
    sql, params = db.executed[0]
    assert "pg_advisory_xact_lock" in sql
    assert params["lock_id"] == 90_210_041


def test_concurrent_appends_produce_single_linear_chain(tmp_path: Path) -> None:
    session_factory = _make_session_factory(tmp_path)

    def worker(index: int) -> None:
        with session_factory() as db:
            append_audit_entry(
                db,
                action="audit.concurrent.test",
                entity_type="audit",
                entity_id=str(index),
                actor_id=f"admin-{index}",
                actor_role="admin",
                actor_auth_method="jwt",
                request_id=f"req-{index}",
                payload={"index": index},
            )
            db.commit()

    worker_count = 12
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        list(executor.map(worker, range(worker_count)))

    with session_factory() as db:
        rows = db.query(AuditLog).order_by(AuditLog.id.asc()).all()
        result = verify_chain(db)

    assert len(rows) == worker_count
    assert result.ok is True, f"unexpected chain violations: {result.violations}"
    assert result.entries_checked == worker_count
