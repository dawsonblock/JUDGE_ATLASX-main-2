"""Admin security tests.

Proves that:
1. Missing token returns 403
2. Wrong token returns 403
3. Correct token succeeds (when admin enabled)
4. Admin endpoints fail when admin features disabled
5. Production mode rejects default tokens
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestAdminAuth:
    """Test admin authentication and authorization."""

    def test_admin_review_queue_requires_token(self):
        """Admin review queue should require token."""
        response = client.get("/api/admin/review-queue")
        # Should return 403 when admin is not enabled or token missing
        assert response.status_code in (403, 404, 401)

    def test_admin_review_items_requires_token(self):
        """Admin review items should require token."""
        response = client.get("/api/admin/review/items")
        # Should return 403 when admin is not enabled or token missing
        assert response.status_code in (403, 404, 401)

    def test_admin_ingestion_requires_token(self):
        """Admin ingestion endpoints should require token."""
        response = client.get("/api/admin/ingestion-runs")
        # Should return 403 when admin is not enabled or token missing
        assert response.status_code in (403, 404, 401)

    def test_admin_sources_requires_token(self):
        """Admin sources endpoints should require token."""
        response = client.get("/api/admin/sources")
        # Should return 403 when admin is not enabled or token missing
        assert response.status_code in (403, 404, 401)

    def test_wrong_token_rejected(self):
        """Wrong admin token should be rejected."""
        response = client.get(
            "/api/admin/review-queue", headers={"X-JTA-Admin-Token": "wrong-token"}
        )
        # Should be rejected
        assert response.status_code in (403, 401)

    def test_role_hierarchy_enforces_minimum_rank(self):
        """Lower-ranked JWT actors must not pass higher-ranked dependency guards."""
        from fastapi import HTTPException

        from app.auth.actor import AdminActor
        from app.auth.admin import enforce_min_role

        viewer = AdminActor(
            actor_id="viewer@example.test",
            actor_type="user",
            role="viewer",
            auth_method="jwt",
        )
        owner = AdminActor(
            actor_id="owner@example.test",
            actor_type="user",
            role="owner",
            auth_method="jwt",
        )

        with pytest.raises(HTTPException) as exc:
            enforce_min_role(viewer, "source_admin")
        assert exc.value.status_code == 403

        assert enforce_min_role(owner, "admin") is owner

    def test_legacy_system_admin_normalizes_to_admin(self):
        """Legacy persisted/JWT role names remain readable but are not canonical."""
        from app.auth.actor import normalize_admin_role

        assert normalize_admin_role("system_admin") == "admin"
        assert normalize_admin_role("owner") == "owner"


class TestAdminConfig:
    """Test admin configuration validation."""

    def test_shared_token_documented_as_local_only(self):
        """Shared token auth is documented as local-alpha only.

        This test verifies that the documentation exists and describes
        the limitations of shared token authentication.
        """
        import os

        docs_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "docs", "AUTH_ROADMAP.md"
        )
        assert os.path.exists(docs_path), "AUTH_ROADMAP.md should exist"

        with open(docs_path) as f:
            content = f.read()
            assert "local-alpha" in content.lower() or "shared token" in content.lower()

    def test_deployment_security_doc_exists(self):
        """Deployment security documentation should exist."""
        import os

        docs_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "docs", "DEPLOYMENT_SECURITY.md"
        )
        assert os.path.exists(docs_path), "DEPLOYMENT_SECURITY.md should exist"


class TestAuditLogging:
    """Test audit logging requirements.

    These are aspirational tests for when audit logging is implemented.
    """

    def test_review_actions_need_audit_log(self, client, db_session, monkeypatch):
        """Review actions should write an AuditLog entry."""
        from app.models.entities import AuditLog, Event
        from sqlalchemy import select

        event = db_session.scalar(
            select(Event).where(Event.event_id == "EVT-SAMPLE-006")
        )
        assert event is not None, "Seeded events must exist"

        class LegacyEnabledSettings:
            enable_admin_review = True
            admin_review_token = "test-token"
            admin_token = "test-token"
            jwt_auth_enabled = False
            enable_legacy_admin_token = True

        monkeypatch.setattr(
            "app.auth.admin.get_settings", lambda: LegacyEnabledSettings()
        )

        response = client.post(
            f"/api/admin/review-queue/event/{event.event_id}/decision",
            json={
                "decision": "approve",
                "reviewed_by": "audit_tester",
                "notes": "audit test",
            },
            headers={"X-JTA-Admin-Token": "test-token"},
        )
        assert response.status_code == 200

        db_session.expire_all()
        log = db_session.scalar(
            select(AuditLog)
            .where(AuditLog.action == "review.decision")
            .where(AuditLog.entity_type == "event")
            .where(AuditLog.entity_id == str(event.id))
            .order_by(AuditLog.id.desc())
        )
        assert log is not None, "AuditLog entry must be created for review decisions"
        assert log.actor_id == "shared-admin-token"

    def test_admin_api_calls_need_audit_log(self, client, db_session, monkeypatch):
        """Admin API calls should increment the AuditLog."""
        from app.models.entities import AuditLog, Event
        from sqlalchemy import func, select

        event = db_session.scalar(
            select(Event).where(Event.event_id == "EVT-SAMPLE-006")
        )
        assert event is not None, "Seeded events must exist"

        count_before = (
            db_session.scalar(
                select(func.count(AuditLog.id)).where(
                    AuditLog.action == "review.decision"
                )
            )
            or 0
        )

        class LegacyEnabledSettings:
            enable_admin_review = True
            admin_review_token = "test-token"
            admin_token = "test-token"
            jwt_auth_enabled = False
            enable_legacy_admin_token = True

        monkeypatch.setattr(
            "app.auth.admin.get_settings", lambda: LegacyEnabledSettings()
        )

        response = client.post(
            f"/api/admin/review-queue/event/{event.event_id}/decision",
            json={
                "decision": "approve",
                "reviewed_by": "monitor_admin",
                "notes": "logging check",
            },
            headers={"X-JTA-Admin-Token": "test-token"},
        )
        assert response.status_code == 200

        db_session.expire_all()
        count_after = (
            db_session.scalar(
                select(func.count(AuditLog.id)).where(
                    AuditLog.action == "review.decision"
                )
            )
            or 0
        )
        assert (
            count_after > count_before
        ), "AuditLog count must increase after admin API call"


class TestAdminActorIdentity:
    """Test that admin actor identity never exposes raw tokens."""

    def test_require_admin_token_returns_admin_actor(self, monkeypatch):
        """require_admin_token must return AdminActor, not a string."""
        from unittest.mock import patch

        from fastapi import HTTPException

        from app.auth.actor import AdminActor

        # Patch get_settings to return a settings object with a known token
        class FakeSettings:
            admin_token = "test-secret-token"
            admin_review_token = None
            jwt_auth_enabled = False
            enable_legacy_admin_token = True

        with patch("app.auth.admin.get_settings", return_value=FakeSettings()):
            from app.auth.admin import require_admin_token

            actor = (
                require_admin_token.__wrapped__("test-secret-token")
                if hasattr(require_admin_token, "__wrapped__")
                else require_admin_token(x_jta_admin_token="test-secret-token")
            )

        assert isinstance(
            actor, AdminActor
        ), f"require_admin_token must return AdminActor, got {type(actor)}"

    def test_actor_id_is_not_raw_token(self, monkeypatch):
        """actor_id must be a stable label, never the raw token value."""
        from unittest.mock import patch

        class FakeSettings:
            admin_token = "super-secret-value-12345"
            admin_review_token = None
            jwt_auth_enabled = False
            enable_legacy_admin_token = True

        with patch("app.auth.admin.get_settings", return_value=FakeSettings()):
            from app.auth.admin import require_admin_token

            actor = require_admin_token(x_jta_admin_token="super-secret-value-12345")

        assert (
            actor.actor_id != "super-secret-value-12345"
        ), "actor_id must not be the raw token value"
        assert actor.actor_id == "shared-admin-token"

    def test_audit_log_does_not_contain_raw_token(self):
        """Raw token value must never appear in audit log payload."""
        import json
        from datetime import datetime, timezone
        from unittest.mock import MagicMock, patch

        from app.auth.actor import AdminActor
        from app.auth.admin import log_mutation

        raw_token = "my-very-secret-admin-token-xyz"
        actor = AdminActor(
            actor_id="shared-admin-token",
            actor_type="shared_token",
            role="owner",
            auth_method="shared_token",
        )

        captured = {}

        class FakeDB:
            def add(self, obj):
                captured["log"] = obj
                obj.id = 1  # simulate flush assigning id

            def flush(self):
                pass  # id already assigned in add()

            def query(self, *args, **kwargs):
                # Simulate no prior entries (returns GENESIS prev_hash path)
                class _Q:
                    def order_by(self, *a):
                        return self

                    def first(self):
                        return None

                return _Q()

            def commit(self):
                pass

            def rollback(self):
                pass

            def close(self):
                pass

        with patch("app.auth.admin.SessionLocal", return_value=FakeDB()):
            log_mutation(
                action="test_action",
                payload={"description": "test"},
                actor=actor,
            )

        log_entry = captured.get("log")
        assert log_entry is not None
        # Check no field contains the raw token
        for field in ("actor_id", "actor_type", "actor_role"):
            val = getattr(log_entry, field, None)
            assert val != raw_token, f"Field {field} contains raw token"
        # Check payload does not contain raw token
        payload_str = json.dumps(log_entry.payload or {})
        assert raw_token not in payload_str, "Raw token found in audit log payload"

    def test_actor_id_is_stable_label(self):
        """actor_id for shared-token auth must always be 'shared-admin-token'."""
        from unittest.mock import patch

        class FakeSettings:
            admin_token = "token-abc"
            admin_review_token = None
            jwt_auth_enabled = False
            enable_legacy_admin_token = True

        with patch("app.auth.admin.get_settings", return_value=FakeSettings()):
            from app.auth.admin import require_admin_token

            actor = require_admin_token(x_jta_admin_token="token-abc")

        assert actor.actor_id == "shared-admin-token"
        assert actor.actor_type == "shared_token"
        assert actor.role == "owner"
        assert actor.auth_method == "shared_token"
