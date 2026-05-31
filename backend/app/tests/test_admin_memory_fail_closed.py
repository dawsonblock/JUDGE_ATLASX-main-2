from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.routes.admin_memory import (
    InvalidateClaimRequest,
    invalidate_claim_endpoint,
)


def test_invalidate_claim_fails_closed_when_audit_write_fails() -> None:
    db = MagicMock()
    actor = MagicMock(auth_method="jwt")
    fake_audit = MagicMock(id=88)

    with (
        patch(
            "app.api.routes.admin_memory.invalidate_claim",
            return_value=fake_audit,
        ),
        patch(
            "app.api.routes.admin_memory.log_mutation",
            side_effect=RuntimeError("audit down"),
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            invalidate_claim_endpoint(
                claim_id=42,
                body=InvalidateClaimRequest(reason="manual_reject"),
                request=MagicMock(),
                actor=actor,
                db=db,
            )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Audit logging failed; mutation aborted"
    db.rollback.assert_called_once()
    db.commit.assert_not_called()
