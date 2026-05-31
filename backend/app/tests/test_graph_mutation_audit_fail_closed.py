from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.routes.graph import EdgeCreateRequest, create_edge


def _request() -> EdgeCreateRequest:
    return EdgeCreateRequest(
        subject_type="judge",
        subject_id=1,
        predicate="presided_over",
        object_type="case",
        object_id=2,
    )


def test_graph_edge_create_fails_closed_when_audit_write_fails() -> None:
    db = MagicMock()
    actor = MagicMock(actor_id="admin@example.com")
    edge = MagicMock(
        id=123,
        subject_type="judge",
        subject_id=1,
        predicate="presided_over",
        object_type="case",
        object_id=2,
        evidence_refs=None,
        valid_from=None,
        valid_until=None,
        status="active",
        created_by="admin@example.com",
    )

    with (
        patch("app.api.routes.graph.GraphQueryService") as svc_cls,
        patch("app.api.routes.graph.log_mutation", side_effect=RuntimeError("audit down")),
    ):
        svc = svc_cls.return_value
        svc.create_edge.return_value = edge

        with pytest.raises(HTTPException) as exc_info:
            create_edge(request=_request(), db=db, actor=actor)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Audit logging failed; mutation aborted"
    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def test_graph_edge_create_returns_400_for_service_errors() -> None:
    db = MagicMock()
    actor = MagicMock(actor_id="admin@example.com")

    with patch("app.api.routes.graph.GraphQueryService") as svc_cls:
        svc = svc_cls.return_value
        svc.create_edge.side_effect = RuntimeError("invalid edge")

        with pytest.raises(HTTPException) as exc_info:
            create_edge(request=_request(), db=db, actor=actor)

    assert exc_info.value.status_code == 400
    assert "invalid edge" in str(exc_info.value.detail)
    db.rollback.assert_called_once()
