import hmac
import logging
from typing import Any

from fastapi import Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.audit.append_log import append_audit_entry
from app.auth.actor import AdminActor, normalize_admin_role
from app.auth.jwt_handler import decode_token
from app.core.config import Settings, get_settings
from app.db.session import SessionLocal

_TOKEN_ROLE_IMPORTS = "import"
_TOKEN_ROLE_REVIEW = "review"
_TOKEN_ROLE_ADMIN = "admin"

# Role hierarchy: lower rank = fewer privileges.
ROLE_RANK: dict[str, int] = {
    "viewer": 0,
    "reviewer": 1,
    "source_admin": 2,
    "admin": 3,
    "owner": 4,
    # Legacy persisted/JWT role name; normalized on new auth paths.
    "system_admin": 3,
}


def enforce_min_role(actor: "AdminActor", required: str) -> "AdminActor":
    """Raise 403 if actor's role does not meet *required* rank; else return actor."""
    required_role = normalize_admin_role(required)
    actor_role = normalize_admin_role(actor.role)
    if ROLE_RANK.get(actor_role, -1) < ROLE_RANK[required_role]:
        raise HTTPException(
            status_code=403,
            detail=f"Role '{actor_role}' is insufficient; '{required_role}' or higher required.",
        )
    return actor


def _compare_token(provided: str | None, expected: str | None) -> bool:
    """Constant-time token comparison using hmac.compare_digest."""
    if not provided or not expected:
        return False
    return hmac.compare_digest(provided.encode(), expected.encode())


def _require_token_for_role(
    settings: Settings,
    x_jta_admin_token: str | None,
    role: str,
) -> None:
    """Fail closed with 403 if token does not match the required role."""
    if role == _TOKEN_ROLE_IMPORTS:
        token = settings.admin_token
        configured = bool(token)
    elif role == _TOKEN_ROLE_REVIEW:
        token = settings.admin_review_token or settings.admin_token
        configured = bool(token)
    else:
        token = settings.admin_token or settings.admin_review_token
        configured = bool(token)

    if not configured:
        raise HTTPException(
            status_code=403,
            detail=f"Admin token not configured for role: {role}",
        )
    if not _compare_token(x_jta_admin_token, token):
        raise HTTPException(status_code=403, detail="Invalid admin token")


def require_admin_imports(
    x_jta_admin_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> AdminActor:
    """Require a valid admin credential with import authority.

    Mirrors ``require_admin_token`` but also gates on ``enable_admin_imports``.
    JWT Bearer token is accepted when ``jwt_auth_enabled=True``; falls back to
    the legacy shared-token path only when ``enable_legacy_admin_token=True``.

    Returns an ``AdminActor`` (never ``None``) so callers can pass the actor to
    ``enforce_jwt_mutation_authority`` and ``log_mutation`` without a null check.
    """
    settings = get_settings()
    if not settings.enable_admin_imports:
        raise HTTPException(status_code=403, detail="Admin imports are disabled")

    jwt_auth_enabled = getattr(settings, "jwt_auth_enabled", False)
    if jwt_auth_enabled and authorization and authorization.startswith("Bearer "):
        raw_token = authorization.removeprefix("Bearer ").strip()
        try:
            payload = decode_token(raw_token)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc))
        if payload.token_type != "access":
            raise HTTPException(status_code=401, detail="Access token required")
        return AdminActor(
            actor_id=payload.email,
            actor_type="user",
            role=normalize_admin_role(payload.role),
            auth_method="jwt",
            email=payload.email,
        )

    if not getattr(settings, "enable_legacy_admin_token", True):
        raise HTTPException(
            status_code=403,
            detail=(
                "Legacy shared-token authentication is disabled. "
                "Use JWT Bearer token authentication instead."
            ),
        )

    _require_token_for_role(settings, x_jta_admin_token, _TOKEN_ROLE_IMPORTS)
    import warnings
    warnings.warn(
        "Shared-token import authentication is deprecated and will be removed. "
        "Migrate to JWT authentication.",
        DeprecationWarning,
        stacklevel=2,
    )
    return AdminActor(
        actor_id="shared-admin-token",
        actor_type="shared_token",
        role="admin",
        auth_method="shared_token",
    )


def require_admin_review(
    x_jta_admin_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> AdminActor:
    settings = get_settings()
    if not settings.enable_admin_review:
        raise HTTPException(status_code=403, detail="Admin review is disabled")
    return require_reviewer(x_jta_admin_token, authorization)


# AUTH GAP — shared-token limitations (see docs/AUTH_ROADMAP.md for upgrade path):
#   1. All valid tokens produce actor_id="shared-admin-token" — no per-user attribution.
#   2. Tokens never expire — a leaked token requires a redeploy to revoke.
#   3. No role separation at the *identity* level: reviewer and importer roles are
#      enforced by which endpoint is called, not by separate credentials.
#   4. No MFA or second-factor support.
#   5. Concurrent sessions from multiple operators are indistinguishable in audit logs.
# Upgrade: AUTH_ROADMAP.md §Phase 2 — replace with OIDC/Clerk/Auth0 JWT verification;
# extract sub claim as actor_id; keep AdminActor shape stable so callsites don't change.
def require_admin_token(
    x_jta_admin_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> AdminActor:
    """Require a valid admin token for general admin operations.

    When ``jwt_auth_enabled=True`` in config, a ``Authorization: Bearer <jwt>``
    header with a valid access token is accepted in addition to the legacy
    ``X-JTA-Admin-Token`` header.  The Bearer JWT path takes precedence.

    Returns an AdminActor with a stable, non-secret actor_id. The raw
    token value is NEVER returned or stored.
    """
    settings = get_settings()
    jwt_auth_enabled = getattr(settings, "jwt_auth_enabled", False)

    # --- JWT path (preferred when jwt_auth_enabled) ---------------------------
    if (
        jwt_auth_enabled
        and authorization
        and authorization.startswith("Bearer ")
    ):
        raw_token = authorization.removeprefix("Bearer ").strip()
        try:
            payload = decode_token(raw_token)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc))
        if payload.token_type != "access":
            raise HTTPException(status_code=401, detail="Access token required")
        return AdminActor(
            actor_id=payload.email,
            actor_type="user",
            role=normalize_admin_role(payload.role),
            auth_method="jwt",
            email=payload.email,
        )

    # --- Legacy shared-token path ---------------------------------------------
    # DEPRECATED: disabled by default via enable_legacy_admin_token=False.
    # Enable only in local development by setting JTA_ENABLE_LEGACY_ADMIN_TOKEN=true.
    if not getattr(settings, "enable_legacy_admin_token", True):
        raise HTTPException(
            status_code=403,
            detail=(
                "Legacy shared-token authentication is disabled. "
                "Use JWT Bearer token authentication instead."
            ),
        )

    token = settings.admin_token or settings.admin_review_token

    if not token:
        raise HTTPException(status_code=403, detail="Admin token not configured")

    if not _compare_token(x_jta_admin_token, token):
        raise HTTPException(status_code=403, detail="Invalid admin token")

    import warnings
    warnings.warn(
        "Shared-token admin authentication is deprecated and will be removed. "
        "Migrate to JWT authentication.",
        DeprecationWarning,
        stacklevel=2,
    )

    # Shared-token mode is development compatibility only; all valid tokens get owner role.
    # actor_id is a stable label — never the raw token value.
    return AdminActor(
        actor_id="shared-admin-token",
        actor_type="shared_token",
        role="owner",
        auth_method="shared_token",
    )


def require_viewer(
    x_jta_admin_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> AdminActor:
    """Require valid admin token with at least viewer role."""
    actor = require_admin_token(x_jta_admin_token, authorization)
    return enforce_min_role(actor, "viewer")


def require_reviewer(
    x_jta_admin_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> AdminActor:
    """Require valid admin token with at least reviewer role."""
    actor = require_admin_token(x_jta_admin_token, authorization)
    return enforce_min_role(actor, "reviewer")


def require_source_admin(
    x_jta_admin_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> AdminActor:
    """Require valid admin token with at least source_admin role."""
    actor = require_admin_token(x_jta_admin_token, authorization)
    return enforce_min_role(actor, "source_admin")


def require_system_admin(
    x_jta_admin_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> AdminActor:
    """Deprecated compatibility wrapper; require at least admin role."""
    actor = require_admin_token(x_jta_admin_token, authorization)
    return enforce_min_role(actor, "admin")


def enforce_jwt_mutation_authority(actor: AdminActor) -> AdminActor:
    """Require JWT-authenticated actor for mutations when configured.

    This is intentionally route-level and opt-in via
    ``settings.enforce_jwt_mutations`` so read-only admin paths can remain
    compatible while mutation authority hardens toward JWT-only.
    """
    settings = get_settings()
    if not getattr(settings, "enforce_jwt_mutations", False):
        return actor
    if actor.auth_method != "jwt":
        raise HTTPException(
            status_code=403,
            detail=(
                "JWT authentication is required for mutation operations. "
                "Shared-token mutation authority is disabled."
            ),
        )
    return actor


def require_public_event_post(
    x_jta_admin_token: str | None = Header(default=None),
) -> None:
    """Require admin token when public event posting is enabled."""
    settings = get_settings()
    if not settings.enable_public_event_post:
        raise HTTPException(status_code=403, detail="Public event posting is disabled")
    _require_token_for_role(settings, x_jta_admin_token, _TOKEN_ROLE_ADMIN)


def require_public_event_actor(
    x_jta_admin_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> AdminActor:
    """Require public-event posting to be enabled and return a reviewer-floor actor."""
    settings = get_settings()
    if not settings.enable_public_event_post:
        raise HTTPException(status_code=403, detail="Public event posting is disabled")
    actor = require_reviewer(x_jta_admin_token, authorization)
    return enforce_jwt_mutation_authority(actor)


def log_mutation(
    action: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    payload: dict[str, Any] | None = None,
    request: Request | None = None,
    token_role: str | None = None,
    actor: AdminActor | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
    db: Session | None = None,
    fail_closed: bool = False,
) -> None:
    """Log a mutation action to the audit log.

    Raw token values must never appear in the payload or actor fields.
    Pass an AdminActor to populate actor identity fields safely.

        Behavior modes:
        - ``db is None`` (default): opens an internal session and commits the
            audit row immediately for backwards compatibility.
        - ``db is not None``: writes inside the caller transaction (no commit).
            Use ``fail_closed=True`` on critical mutation paths so audit write
            failures abort the mutation transaction.
    """
    owns_session = db is None
    session = db or SessionLocal()
    try:
        full_payload: dict[str, Any] = payload or {}
        if token_role:
            full_payload = {**full_payload, "token_role": token_role}

        resolved_user_agent = user_agent
        if resolved_user_agent is None and request is not None:
            resolved_user_agent = request.headers.get("user-agent")

        append_audit_entry(
            session,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=full_payload,
            actor_ip=(request.client.host if request and request.client else None),
            actor_id=actor.actor_id if actor else None,
            actor_type=actor.actor_type if actor else "system",
            actor_role=actor.role if actor else None,
            actor_auth_method=actor.auth_method if actor else None,
            user_agent=resolved_user_agent,
            request_id=request_id,
        )
        if owns_session:
            session.commit()
    except Exception:
        session.rollback()
        if fail_closed:
            raise
        logging.exception("audit log write failed for action=%s", action)
    finally:
        if owns_session:
            session.close()
