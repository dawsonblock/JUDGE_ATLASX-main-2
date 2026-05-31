"""Tests for the SourceRegistry is_active gate in IngestionWorker.run().

Verifies that:
- An unregistered source_key raises RuntimeError before any pipeline work.
- A registered but inactive source raises RuntimeError before any pipeline work.
- An active source clears the gate and proceeds to the run-open step.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.db.session import SessionLocal
from app.ingestion.runtime.ingestion_worker import IngestionWorker
from app.models.entities import SourceRegistry


def _uid() -> str:
    return uuid.uuid4().hex[:10]


class TestIngestionSourceGate:
    """Behavioural tests for the is_active gate added to IngestionWorker.run()."""

    def test_unknown_source_key_raises(self) -> None:
        """Running ingestion for an unregistered source_key raises RuntimeError."""
        key = f"ghost-source-{_uid()}"
        with SessionLocal() as db:
            db.query(SourceRegistry).filter(SourceRegistry.source_key == key).delete()
            db.commit()

        mock_adapter = MagicMock()
        with SessionLocal() as db:
            worker = IngestionWorker(db, mock_adapter)
            with pytest.raises(RuntimeError, match="unknown source_key"):
                worker.run(key)

    def test_inactive_source_raises(self) -> None:
        """Running ingestion for an is_active=False source raises RuntimeError."""
        key = f"inactive-source-{_uid()}"
        with SessionLocal() as db:
            reg = SourceRegistry(
                source_key=key,
                source_name="Inactive Test Source",
                is_active=False,
            )
            db.add(reg)
            db.commit()

        mock_adapter = MagicMock()
        with SessionLocal() as db:
            worker = IngestionWorker(db, mock_adapter)
            with pytest.raises(RuntimeError, match="is_active=False"):
                worker.run(key)

    def test_active_source_proceeds_past_gate(self) -> None:
        """Active source clears the gate and advances to the run-open step.

        We patch ingestion_log.open_run to raise a sentinel ValueError so
        that the test does not need a fully-wired pipeline — the only
        assertion is that the gate RuntimeError is NOT what fires.
        """
        key = f"active-source-{_uid()}"
        with SessionLocal() as db:
            reg = SourceRegistry(
                source_key=key,
                source_name="Active Test Source",
                is_active=True,
            )
            db.add(reg)
            db.commit()

        mock_adapter = MagicMock()
        with SessionLocal() as db:
            worker = IngestionWorker(db, mock_adapter)
            with patch(
                "app.ingestion.runtime.ingestion_worker.ingestion_log.open_run",
                side_effect=ValueError("sentinel-past-gate"),
            ):
                with pytest.raises(ValueError, match="sentinel-past-gate"):
                    worker.run(key)
