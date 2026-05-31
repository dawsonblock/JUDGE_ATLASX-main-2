"""Tests for the evidence vault (Phase C): hashing, provenance, extraction,
and snapshot retrieval with integrity verification."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event, update
from sqlalchemy.orm import Session

from app.db.session import Base
from app.evidence.extraction import extract_text
from app.evidence.hashing import EvidenceIntegrityError, compute_hash, verify_hash
from app.evidence.hashing import EvidenceIntegrityError, compute_hash, verify_hash
from app.evidence.provenance import (
    CUSTODY_ACTIONS,
    build_chain_of_custody,
    record_custody_event,
)
from app.evidence.snapshots import retrieve_and_verify
from app.models.entities import SourceSnapshot
from app.services.snapshot_writer import write_snapshot

# ---------------------------------------------------------------------------
# Fixture: in-memory SQLite session with full schema
# ---------------------------------------------------------------------------


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


class TestComputeHash:
    def test_known_value(self):
        data = b"hello"
        expected = hashlib.sha256(b"hello").hexdigest()
        assert compute_hash(data) == expected

    def test_empty_bytes(self):
        h = compute_hash(b"")
        assert len(h) == 64  # hex SHA-256

    def test_same_input_same_output(self):
        data = b"judicial review: R v Smith"
        assert compute_hash(data) == compute_hash(data)

    def test_different_inputs_differ(self):
        assert compute_hash(b"abc") != compute_hash(b"abd")


class TestVerifyHash:
    def test_happy_path(self):
        data = b"case record"
        h = compute_hash(data)
        assert verify_hash(data, h) is True

    def test_mismatch(self):
        data = b"original"
        wrong_hash = compute_hash(b"tampered")
        assert verify_hash(data, wrong_hash) is False


class TestEvidenceIntegrityError:
    def test_attributes(self):
        err = EvidenceIntegrityError(42, "aabbcc", "112233")
        assert err.snapshot_id == 42
        assert err.expected == "aabbcc"
        assert err.actual == "112233"

    def test_message_contains_snapshot_id(self):
        err = EvidenceIntegrityError(99, "a" * 64, "b" * 64)
        assert "99" in str(err)

    def test_is_exception(self):
        with pytest.raises(EvidenceIntegrityError):
            raise EvidenceIntegrityError(1, "e", "a")


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------


class TestExtractText:
    def test_plain_utf8(self):
        text = "Section 7 of the Charter"
        result = extract_text(text.encode("utf-8"))
        assert "Section 7" in result

    def test_html_strips_tags(self):
        html = b"<html><body><h1>Charter</h1><p>Section 7</p></body></html>"
        result = extract_text(html, content_type="text/html")
        assert "Charter" in result
        assert "Section 7" in result
        # HTML tags should not appear in extracted text
        assert "<h1>" not in result

    def test_html_auto_detection_by_magic(self):
        html = b"<!DOCTYPE html><html><body>Judicial decision</body></html>"
        result = extract_text(html)
        assert "Judicial decision" in result

    def test_empty_bytes_returns_string(self):
        result = extract_text(b"")
        assert isinstance(result, str)

    def test_binary_garbage_does_not_raise(self):
        garbage = bytes(range(256))
        result = extract_text(garbage)
        assert isinstance(result, str)

    def test_utf8_with_explicit_content_type(self):
        result = extract_text(b"plain evidence text", content_type="text/plain")
        assert "plain evidence text" in result


# ---------------------------------------------------------------------------
# Provenance: record_custody_event + build_chain_of_custody
# ---------------------------------------------------------------------------


class TestCustodyActions:
    def test_required_actions_present(self):
        required = {
            "created",
            "accessed",
            "verified",
            "failed_verification",
            "quarantined",
        }
        assert required <= CUSTODY_ACTIONS


class TestRecordCustodyEvent:
    def test_creates_log_entry(self, db):
        snap = write_snapshot(db, "http://example.com/", _now(), b"evidence bytes")
        db.flush()

        entry = record_custody_event(db, snap, "accessed")
        db.flush()

        from app.models.entities import ChainOfCustodyLog

        rows = db.query(ChainOfCustodyLog).filter_by(snapshot_id=snap.id).all()
        assert len(rows) >= 1
        actions = [r.action for r in rows]
        assert "accessed" in actions

    def test_default_actor_is_system(self, db):
        snap = write_snapshot(db, "http://example.com/a", _now(), b"content")
        db.flush()

        entry = record_custody_event(db, snap, "verified")
        assert entry.actor == "system"
        assert entry.actor_type == "system"

    def test_custom_actor_stored(self, db):
        snap = write_snapshot(db, "http://example.com/b", _now(), b"content2")
        db.flush()

        entry = record_custody_event(
            db, snap, "exported", actor="admin@court.ca", actor_type="admin"
        )
        assert entry.actor == "admin@court.ca"
        assert entry.actor_type == "admin"

    def test_notes_stored(self, db):
        snap = write_snapshot(db, "http://example.com/c", _now(), b"content3")
        db.flush()

        entry = record_custody_event(
            db, snap, "quarantined", notes="suspected tampering"
        )
        assert entry.notes == "suspected tampering"

    def test_returns_chain_of_custody_log(self, db):
        from app.models.entities import ChainOfCustodyLog

        snap = write_snapshot(db, "http://example.com/d", _now(), b"data")
        db.flush()
        entry = record_custody_event(db, snap, "created")
        assert isinstance(entry, ChainOfCustodyLog)


class TestBuildChainOfCustody:
    def test_empty_for_unknown_snapshot(self, db):
        result = build_chain_of_custody(999_999, db)
        assert result == []

    def test_ordered_ascending(self, db):
        snap = write_snapshot(db, "http://example.com/order", _now(), b"ordered")
        db.flush()

        record_custody_event(db, snap, "created")
        record_custody_event(db, snap, "accessed")
        record_custody_event(db, snap, "verified")
        db.flush()

        entries = build_chain_of_custody(snap.id, db)
        assert len(entries) >= 3
        actions = [e.action for e in entries]
        # "created" must come before "accessed" which must come before "verified"
        assert actions.index("created") < actions.index("verified")

    def test_only_returns_entries_for_snapshot(self, db):
        snap_a = write_snapshot(db, "http://example.com/a2", _now(), b"snap_a")
        snap_b = write_snapshot(db, "http://example.com/b2", _now(), b"snap_b")
        db.flush()

        record_custody_event(db, snap_a, "accessed")
        record_custody_event(db, snap_b, "exported")
        db.flush()

        entries_a = build_chain_of_custody(snap_a.id, db)
        entry_actions = [e.action for e in entries_a]
        assert "exported" not in entry_actions


# ---------------------------------------------------------------------------
# retrieve_and_verify
# ---------------------------------------------------------------------------


class TestRetrieveAndVerify:
    def test_happy_path(self, db):
        content = b"<p>verified judgment</p>"
        snap = write_snapshot(db, "http://example.com/verify", _now(), content)
        db.commit()
        db.refresh(snap)

        returned_snap, returned_content = retrieve_and_verify(snap.id, db)
        assert returned_snap.id == snap.id
        assert returned_content == content

    def test_not_found_raises_value_error(self, db):
        with pytest.raises(ValueError, match="not found"):
            retrieve_and_verify(999_999, db)

    def test_hash_mismatch_raises_integrity_error(self, db):
        content = b"original content for hashing"
        snap = write_snapshot(db, "http://example.com/tamper", _now(), content)
        db.commit()
        db.refresh(snap)

        # Simulate out-of-band tampering directly at the row level.
        db.execute(
            update(SourceSnapshot)
            .where(SourceSnapshot.id == snap.id)
            .values(original_content_hash="0" * 64, content_hash="0" * 64)
        )
        db.commit()

        with pytest.raises(EvidenceIntegrityError) as exc_info:
            retrieve_and_verify(snap.id, db)
        assert exc_info.value.snapshot_id == snap.id
