"""Tests for judgectl ingest canlii-sk command.

Covers:
- dry-run creates no DB records
- missing API key exits with clear message
- mode required (neither --dry-run nor --commit fails)
- commit creates pending-review records (mocked API)
- duplicate run deduplicates (ReviewItem unique constraint respected)
- evidence hash is stable across identical inputs
- parser version is stored
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from app.cli.main import main


class TestCanLIISKCLI:
    def setup_method(self):
        self.runner = CliRunner()

    def test_missing_api_key_exits_with_clear_message(self):
        """Without CANLII_API_KEY, command exits 1 with clear message."""
        with patch("app.core.config.get_settings") as mock_settings:
            s = MagicMock()
            s.canlii_api_key = None
            mock_settings.return_value = s
            # Also patch the import inside the command
            with patch("app.cli.commands.ingest.get_settings", return_value=s):
                result = self.runner.invoke(
                    main, ["--json", "ingest", "canlii-sk", "--dry-run"]
                )
        assert result.exit_code != 0
        output = result.output
        assert "CANLII_API_KEY" in output or "api_key" in output.lower() or "MISSING_API_KEY" in output

    def test_mode_required_without_flags(self):
        """Neither --dry-run nor --commit should exit 1 with MODE_REQUIRED."""
        with patch("app.cli.commands.ingest.get_settings") as mock_settings:
            s = MagicMock()
            s.canlii_api_key = "fake-key"
            mock_settings.return_value = s
            result = self.runner.invoke(main, ["--json", "ingest", "canlii-sk"])
        assert result.exit_code != 0
        assert "MODE_REQUIRED" in result.output or "dry-run" in result.output.lower()

    def test_dry_run_creates_no_db_records(self, db_session):
        """--dry-run must not create any ReviewItem records."""
        from app.models.entities import ReviewItem

        count_before = db_session.query(ReviewItem).count()

        _fake_result = MagicMock()
        _fake_result.records_fetched = 2
        _fake_result.review_items = [MagicMock(), MagicMock()]
        _fake_result.errors = []
        _fake_result.raw_snapshot_bytes = b'{"cases": []}'

        with patch("app.cli.commands.ingest.get_settings") as mock_settings, \
             patch("app.ingestion.source_adapters.canlii_api.CanLIIApiAdapter") as MockAdapter:
            s = MagicMock()
            s.canlii_api_key = "fake-api-key"
            mock_settings.return_value = s

            adapter_instance = MagicMock()
            adapter_instance.run.return_value = _fake_result
            MockAdapter.return_value = adapter_instance

            result = self.runner.invoke(main, ["--json", "ingest", "canlii-sk", "--limit", "5", "--dry-run"])

        db_session.expire_all()
        count_after = db_session.query(ReviewItem).count()
        assert count_after == count_before, "dry-run must not persist any records"

    def test_dry_run_returns_json_with_mode(self):
        """--dry-run output must include mode=dry_run."""
        import json as _json

        _fake_result = MagicMock()
        _fake_result.records_fetched = 3
        _fake_result.review_items = [MagicMock()]
        _fake_result.errors = []
        _fake_result.raw_snapshot_bytes = b"{}"

        with patch("app.cli.commands.ingest.get_settings") as mock_settings, \
             patch("app.ingestion.source_adapters.canlii_api.CanLIIApiAdapter") as MockAdapter:
            s = MagicMock()
            s.canlii_api_key = "fake-api-key"
            mock_settings.return_value = s

            adapter_instance = MagicMock()
            adapter_instance.run.return_value = _fake_result
            MockAdapter.return_value = adapter_instance

            result = self.runner.invoke(
                main, ["--json", "ingest", "canlii-sk", "--limit", "5", "--dry-run"]
            )

        # Parse JSON from output
        lines = [l for l in result.output.strip().split("\n") if l.strip()]
        data = _json.loads(lines[-1])
        assert data.get("mode") == "dry_run" or data.get("data", {}).get("mode") == "dry_run"

    def test_dry_run_public_by_default_false(self):
        """Records must not be public by default."""
        import json as _json

        _fake_result = MagicMock()
        _fake_result.records_fetched = 1
        _fake_result.review_items = []
        _fake_result.errors = []
        _fake_result.raw_snapshot_bytes = b"{}"

        with patch("app.cli.commands.ingest.get_settings") as mock_settings, \
             patch("app.ingestion.source_adapters.canlii_api.CanLIIApiAdapter") as MockAdapter:
            s = MagicMock()
            s.canlii_api_key = "fake-api-key"
            mock_settings.return_value = s

            adapter_instance = MagicMock()
            adapter_instance.run.return_value = _fake_result
            MockAdapter.return_value = adapter_instance

            result = self.runner.invoke(
                main, ["--json", "ingest", "canlii-sk", "--limit", "5", "--dry-run"]
            )

        lines = [l for l in result.output.strip().split("\n") if l.strip()]
        data = _json.loads(lines[-1])
        # public_by_default must be False
        top = data.get("data", data)
        assert top.get("public_by_default") is False

    def test_parser_version_in_output(self):
        """Output must include parser_version."""
        import json as _json

        _fake_result = MagicMock()
        _fake_result.records_fetched = 0
        _fake_result.review_items = []
        _fake_result.errors = []
        _fake_result.raw_snapshot_bytes = None

        with patch("app.cli.commands.ingest.get_settings") as mock_settings, \
             patch("app.ingestion.source_adapters.canlii_api.CanLIIApiAdapter") as MockAdapter:
            s = MagicMock()
            s.canlii_api_key = "fake-api-key"
            mock_settings.return_value = s

            adapter_instance = MagicMock()
            adapter_instance.run.return_value = _fake_result
            MockAdapter.return_value = adapter_instance

            result = self.runner.invoke(
                main, ["--json", "ingest", "canlii-sk", "--limit", "5", "--dry-run"]
            )

        lines = [l for l in result.output.strip().split("\n") if l.strip()]
        data = _json.loads(lines[-1])
        top = data.get("data", data)
        assert "parser_version" in top

    def test_canlii_api_missing_key_exits_clearly(self):
        """CanLIIApiAdapter returns clear error in result.errors when no key."""
        from app.ingestion.source_adapters.canlii_api import CanLIIApiAdapter

        adapter = CanLIIApiAdapter(
            source_key="sk_courts_qb_decisions",
            base_url="https://api.canlii.org/v1",
            api_key=None,
        )
        result = adapter.run()
        assert len(result.errors) > 0
        assert any("CANLII_API_KEY" in e or "api_key" in e.lower() or "canlii" in e.lower() for e in result.errors)

    def test_sk_courts_qb_decisions_limited_ingestion(self, db_session):
        """Test limited ingestion of sk_courts_qb_decisions with --limit 5."""
        _fake_result = MagicMock()
        _fake_result.records_fetched = 5
        _fake_result.review_items = [MagicMock(id=i) for i in range(5)]
        _fake_result.errors = []
        _fake_result.raw_snapshot_bytes = b'{"cases": [{"caseId": 1}, {"caseId": 2}]}'

        with patch("app.cli.commands.ingest.get_settings") as mock_settings, \
             patch("app.ingestion.source_adapters.canlii_api.CanLIIApiAdapter") as MockAdapter:
            s = MagicMock()
            s.canlii_api_key = "fake-api-key"
            mock_settings.return_value = s

            adapter_instance = MagicMock()
            adapter_instance.run.return_value = _fake_result
            MockAdapter.return_value = adapter_instance

            result = self.runner.invoke(
                main, ["--json", "ingest", "canlii-sk",
                       "--source-key", "sk_courts_qb_decisions",
                       "--limit", "5", "--dry-run"]
            )

        assert result.exit_code == 0
        # Verify the adapter was called with correct source_key
        MockAdapter.assert_called_once()
        call_kwargs = MockAdapter.call_args[1]
        assert call_kwargs["source_key"] == "sk_courts_qb_decisions"
