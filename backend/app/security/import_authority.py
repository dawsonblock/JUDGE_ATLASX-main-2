"""Import authority dependencies for admin mutation routes.

This module is intentionally a real authority layer, not just a re-export.
It centralizes the import/ingestion/review role floors so route files can
depend on a clear security boundary instead of calling the broad admin token
dependency directly.
"""

from __future__ import annotations

from fastapi import Header

from app.auth.actor import AdminActor
from app.auth.admin import (
    enforce_jwt_mutation_authority,
    require_admin_imports,
    require_admin_review,
    require_admin_token,
)
from app.security.rbac import require_min_role


def _require_import_floor(
    required_role: str,
    x_jta_admin_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> AdminActor:
    actor = require_admin_imports(
        x_jta_admin_token=x_jta_admin_token,
        authorization=authorization,
    )
    enforce_jwt_mutation_authority(actor)
    return require_min_role(actor, required_role)


def require_import_actor(
    x_jta_admin_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> AdminActor:
    return _require_import_floor(
        "source_admin",
        x_jta_admin_token=x_jta_admin_token,
        authorization=authorization,
    )


def require_source_admin_actor(
    x_jta_admin_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> AdminActor:
    actor = require_admin_token(
        x_jta_admin_token=x_jta_admin_token,
        authorization=authorization,
    )
    enforce_jwt_mutation_authority(actor)
    return require_min_role(actor, "source_admin")


def require_ingestion_admin_actor(
    x_jta_admin_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> AdminActor:
    actor = require_admin_token(
        x_jta_admin_token=x_jta_admin_token,
        authorization=authorization,
    )
    enforce_jwt_mutation_authority(actor)
    return require_min_role(actor, "source_admin")


def require_ai_review_actor(
    x_jta_admin_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> AdminActor:
    actor = require_admin_review(
        x_jta_admin_token=x_jta_admin_token,
        authorization=authorization,
    )
    enforce_jwt_mutation_authority(actor)
    return require_min_role(actor, "reviewer")


def require_admin_actor(
    x_jta_admin_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> AdminActor:
    actor = require_admin_token(
        x_jta_admin_token=x_jta_admin_token,
        authorization=authorization,
    )
    enforce_jwt_mutation_authority(actor)
    return require_min_role(actor, "admin")


def require_reviewer_actor(
    x_jta_admin_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> AdminActor:
    """Require at least reviewer role (evidence verify/unverify)."""
    actor = require_admin_token(
        x_jta_admin_token=x_jta_admin_token,
        authorization=authorization,
    )
    enforce_jwt_mutation_authority(actor)
    return require_min_role(actor, "reviewer")


__all__ = [
    "require_ai_review_actor",
    "require_admin_actor",
    "require_import_actor",
    "require_ingestion_admin_actor",
    "require_reviewer_actor",
    "require_source_admin_actor",
]
