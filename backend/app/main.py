import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.api.routes import router
from app.core.config import get_settings
from app.core.runtime_profile import resolve_runtime_profile, validate_runtime_profile
from app.db.session import SessionLocal, engine
from app.db.spatial import initialize_postgis
from app.middleware.request_id import RequestIdMiddleware
from app.models import entities  # noqa: F401
from app.seed.sample_data import seed_sample_data
from app.seed.source_registry import seed_source_registry


def _validate_cors_origins(cors_origins: str, app_env: str) -> list[str]:
    """Validate CORS origins. In production, fail if empty or wildcard."""
    origins = [origin.strip() for origin in cors_origins.split(",") if origin.strip()]

    # In production, reject empty or wildcard origins
    if app_env == "production":
        if not origins:
            print(
                "ERROR: JTA_CORS_ORIGINS required in production. "
                "Set explicit HTTPS URLs."
            )
            sys.exit(1)
        if "*" in origins:
            print(
                "ERROR: Wildcard '*' not allowed in JTA_CORS_ORIGINS "
                "in production mode."
            )
            sys.exit(1)
        # Verify all origins are HTTPS
        non_https = [o for o in origins if not o.startswith("https://")]
        if non_https:
            print(f"ERROR: Non-HTTPS origins not allowed: {non_https}")
            sys.exit(1)

    return origins if origins else ["*"]


_PLACEHOLDER_PATTERNS = (
    "replace_with",
    "replace-with",
    "change-me",
    "changeme",
    "change_me",
    "todo",
    "example",
    "placeholder",
    "default",
    "dev-secret",
    "test-secret",
    "local-secret",
    "test-only",
)


def _is_placeholder_secret(value: str, field_name: str) -> bool:
    """Return True if *value* looks like an unfilled template placeholder.

    Detects the known patterns from .env.example files, very short values,
    and empty strings — all of which are unsafe as production secrets.
    """
    if not value:
        return True
    if len(value) < 32:
        return True
    low = value.lower()
    for pat in _PLACEHOLDER_PATTERNS:
        if pat in low:
            return True
    return False


def _validate_production_safety(settings) -> None:
    """Validate production safety settings. Fail fast if unsafe."""
    if settings.app_env != "production":
        return  # Skip checks outside production

    # Check JWT secret key is not a weak or placeholder value
    if _is_placeholder_secret(settings.jwt_secret_key, "JTA_JWT_SECRET_KEY"):
        print(
            "ERROR: JTA_JWT_SECRET_KEY is a placeholder or too short. "
            "Generate a cryptographically random secret: "
            "python -c 'import secrets; print(secrets.token_urlsafe(48))' "
            "and set JTA_JWT_SECRET_KEY before running in production."
        )
        sys.exit(1)

    # Check first admin bootstrap secret is not a placeholder
    first_admin = getattr(settings, "first_admin_secret", None) or ""
    if first_admin and _is_placeholder_secret(first_admin, "JTA_FIRST_ADMIN_SECRET"):
        print(
            "ERROR: JTA_FIRST_ADMIN_SECRET is a placeholder or too short. "
            "Generate a secure value: "
            "python -c 'import secrets; print(secrets.token_urlsafe(32))' "
            "and set JTA_FIRST_ADMIN_SECRET before running in production."
        )
        sys.exit(1)

    # Require JWT auth to be explicitly enabled in production
    if not settings.jwt_auth_enabled:
        print(
            "ERROR: JTA_JWT_AUTH_ENABLED must be true in production. "
            "Set JTA_JWT_AUTH_ENABLED=true once admin users have been created."
        )
        sys.exit(1)

    # Legacy shared-token admin auth must stay off in production.
    # Fail fast both when the feature flag is enabled and when legacy shared-token
    # secrets are configured at all, because some auth paths may still consult the
    # shared tokens directly.
    legacy_admin_token_configured = bool(getattr(settings, "admin_token", None))
    legacy_review_token_configured = bool(
        getattr(settings, "admin_review_token", None)
    )
    if (
        settings.enable_legacy_admin_token
        or legacy_admin_token_configured
        or legacy_review_token_configured
    ):
        print(
            "ERROR: Legacy shared-token admin authentication is not allowed in "
            "production. Ensure JTA_ENABLE_LEGACY_ADMIN_TOKEN=false and unset "
            "JTA_ADMIN_TOKEN / JTA_ADMIN_REVIEW_TOKEN. Use JWT Bearer "
            "authentication for admin operations."
        )
        sys.exit(1)

    ingestion_queue_backend = getattr(settings, "ingestion_queue_backend", "inprocess")
    # Allow inprocess queue for testing with explicit opt-in
    allow_inprocess_queue = os.environ.get(
        "JTA_ALLOW_INPROCESS_QUEUE_PRODUCTION", ""
    ).lower() in ("1", "true", "yes")
    if ingestion_queue_backend == "inprocess" and not allow_inprocess_queue:
        print(
            "ERROR: JTA_INGESTION_QUEUE_BACKEND=inprocess is not allowed in "
            "production. The in-process queue is alpha-only and not "
            "production-capable. A production-capable queue backend must be "
            "implemented before production deployment."
        )
        sys.exit(1)

    # Reject in-memory rate limiting in production (not safe across multiple workers/replicas)
    # unless the operator explicitly opts in with JTA_ALLOW_IN_MEMORY_RATE_LIMIT_PRODUCTION=true.
    if settings.rate_limit_backend != "redis":
        allow_override = os.environ.get(
            "JTA_ALLOW_IN_MEMORY_RATE_LIMIT_PRODUCTION", ""
        ).lower()
        if allow_override not in ("1", "true", "yes"):
            print(
                "ERROR: JTA_RATE_LIMIT_BACKEND=memory is unsafe in production with "
                "multiple workers or replicas. Set JTA_RATE_LIMIT_BACKEND=redis, or "
                "set JTA_ALLOW_IN_MEMORY_RATE_LIMIT_PRODUCTION=true only for "
                "verified single-node deployments."
            )
            sys.exit(1)

    # Check Redis availability if configured
    if settings.rate_limit_backend == "redis":
        import redis

        try:
            r = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2)
            r.ping()
        except Exception as e:
            print(
                f"ERROR: Redis configured but unavailable in production: {e}. "
                "Rate limiting requires Redis in production."
            )
            sys.exit(1)

    # Require evidence vault in production
    if not settings.evidence_store_required:
        print(
            "ERROR: JTA_EVIDENCE_STORE_REQUIRED must be true in production. "
            "Set JTA_EVIDENCE_STORE_REQUIRED=true and configure JTA_EVIDENCE_STORE_ROOT."
        )
        sys.exit(1)

    # Hard-fail when JTA_FETCH_EGRESS_PROXY is not set in production.
    # All outbound ingestion fetches must route through an egress proxy to
    # mitigate DNS rebinding attacks (see safe_fetch.py § DNS Rebinding).
    # If the deployment enforces egress at the network/infrastructure level
    # instead, set JTA_ALLOW_DIRECT_PROD_FETCH_WITH_NETWORK_POLICY=1 to
    # acknowledge the responsibility and suppress this check.
    if not os.environ.get("JTA_FETCH_EGRESS_PROXY") and not os.environ.get(
        "JTA_ALLOW_DIRECT_PROD_FETCH_WITH_NETWORK_POLICY"
    ):
        print(
            "ERROR: JTA_FETCH_EGRESS_PROXY is not set. Outbound ingestion "
            "fetches are not routed through an egress proxy, which leaves the "
            "service exposed to DNS rebinding attacks. Set JTA_FETCH_EGRESS_PROXY "
            "to an HTTP/HTTPS proxy URL, or set "
            "JTA_ALLOW_DIRECT_PROD_FETCH_WITH_NETWORK_POLICY=1 if egress is "
            "enforced by the infrastructure network policy."
        )
        sys.exit(1)

    # Block alpha queue backends in production without explicit override
    # Both "inprocess" and "postgres" are not production-qualified
    queue_backend = settings.ingestion_queue_backend
    if queue_backend == "postgres":
        # Check environment type
        is_production = settings.app_env == "production"

        if is_production and not settings.allow_alpha_postgres_queue:
            print(
                "ERROR: JTA_INGESTION_QUEUE_BACKEND=postgres is enabled in production "
                "without explicit override. "
                "The PostgreSQL queue backend is alpha-hardened with worker-safe features "
                "(lease_next_job, heartbeat_job, complete_job, fail_job, recover_stale_jobs, "
                "move_to_dead_letter, FOR UPDATE SKIP LOCKED, idempotency_key, rate limits) "
                "but is not yet production-qualified. "
                "To allow alpha postgres queue in production, set "
                "JTA_ALLOW_ALPHA_POSTGRES_QUEUE=true. "
                "A production-qualified queue backend must be implemented "
                "for production deployment."
            )
            sys.exit(1)
        elif is_production and settings.allow_alpha_postgres_queue:
            print(
                "[STARTUP] WARNING: JTA_INGESTION_QUEUE_BACKEND=postgres is enabled "
                "in production with JTA_ALLOW_ALPHA_POSTGRES_QUEUE=true. "
                "This is an alpha-hardened queue backend and should only be used for "
                "controlled production testing. Ensure queue proof tests pass before deployment."
            )
        else:
            print(
                "[STARTUP] JTA_INGESTION_QUEUE_BACKEND=postgres is enabled in alpha mode "
                f"(environment: {settings.app_env}). "
                "Queue capability status: alpha-hardened with worker-safe features. "
                "Production deployment requires JTA_ALLOW_ALPHA_POSTGRES_QUEUE=true."
            )
    if queue_backend not in ("inprocess", "postgres"):
        print(
            f"ERROR: Unknown JTA_INGESTION_QUEUE_BACKEND value: {queue_backend}. "
            "Valid values are 'inprocess' or 'postgres'."
        )
        sys.exit(1)

    print("[STARTUP] Production safety checks passed")


def _check_external_reference_not_loaded() -> None:
    """Verify external_reference modules are not imported into runtime.

    This is a runtime sanity check (complementing the CI gate) to catch
    accidental imports of archived/reference code.
    """
    import sys

    dangerous_prefixes = (
        "external_reference",
        "legacy_disabled",
        "archived_research",
    )

    loaded_external = []
    for module_name in sys.modules:
        for prefix in dangerous_prefixes:
            if module_name.startswith(prefix):
                loaded_external.append(module_name)

    if loaded_external:
        print(
            "[STARTUP WARNING] external_reference modules loaded into runtime. "
            "This should not happen in production. Loaded modules:\n"
            + "\n".join(f"  - {m}" for m in loaded_external),
            file=sys.stderr,
        )


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to limit request body size using Content-Length header."""

    def __init__(self, app, max_size: int):
        super().__init__(app)
        self.max_size = max_size

    async def dispatch(self, request: Request, call_next):
        limit_exceeded = False
        if request.method in ("POST", "PUT", "PATCH"):
            # Check Content-Length header first (cheaper path)
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    size = int(content_length)
                    if size > self.max_size:
                        return JSONResponse(
                            status_code=413,
                            content={
                                "error": "Request too large",
                                "max_size_bytes": self.max_size,
                                "content_length": size,
                            },
                        )
                except ValueError:
                    # Invalid Content-Length value — fall through to streaming check
                    pass
            else:
                # No Content-Length (chunked / streaming upload): wrap receive to
                # enforce byte cap without buffering the whole body at once.
                original_receive = request._receive
                bytes_seen = 0

                async def capped_receive():
                    nonlocal bytes_seen, limit_exceeded
                    message = await original_receive()
                    if message.get("type") == "http.request":
                        chunk = message.get("body", b"")
                        bytes_seen += len(chunk)
                        if bytes_seen > self.max_size:
                            limit_exceeded = True
                            return {
                                "type": "http.request",
                                "body": b"",
                                "more_body": False,
                            }
                    return message

                request._receive = capped_receive
        response = await call_next(request)
        if limit_exceeded:
            return JSONResponse(
                status_code=413,
                content={
                    "error": "Request too large",
                    "max_size_bytes": self.max_size,
                },
            )
        return response


def create_app() -> FastAPI:
    from pathlib import Path
    from app.services.evidence_store_validation import validate_evidence_store_root

    settings = get_settings()

    runtime_profile = resolve_runtime_profile(settings)
    profile_errors, profile_warnings = validate_runtime_profile(settings, runtime_profile)
    for warning in profile_warnings:
        print(f"[STARTUP WARNING] {warning}")
    if profile_errors:
        for error in profile_errors:
            print(f"ERROR: {error}")
        sys.exit(1)

    # Validate production safety before proceeding
    _validate_production_safety(settings)

    if settings.enable_experimental_live_map:
        raise RuntimeError(
            "Experimental live_map cannot be mounted until public/admin boundary tests pass."
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Validate evidence store before initializing database
        try:
            evidence_required = settings.evidence_store_required or settings.app_env == "production"
            validate_evidence_store_root(
                settings.evidence_store_root,
                required=evidence_required,
                probe_write=settings.evidence_store_probe_write,
                repo_root=str(Path(__file__).resolve().parents[2]),
            )
            print("[STARTUP] Evidence store validated")
        except RuntimeError as e:
            print(f"ERROR: Evidence store validation failed: {e}")
            sys.exit(1)

        # Check that external_reference is not accidentally loaded
        _check_external_reference_not_loaded()


        # Warn loudly if the deprecated legacy shared-token admin path is enabled.
        # This path is disabled by default (JTA_ENABLE_LEGACY_ADMIN_TOKEN=false).
        # It should NEVER be enabled in production.
        if settings.enable_legacy_admin_token:
            import warnings
            msg = (
                "[STARTUP WARNING] JTA_ENABLE_LEGACY_ADMIN_TOKEN is enabled. "
                "Shared-token admin authentication is deprecated and insecure. "
                "Disable it (JTA_ENABLE_LEGACY_ADMIN_TOKEN=false) and use JWT authentication. "
                "NEVER enable this in production."
            )
            print(msg, file=sys.stderr)
            warnings.warn(msg, DeprecationWarning, stacklevel=1)

        initialize_postgis(engine)
        # Source registry is seeded independently of sample data (prod-safe)
        if settings.seed_source_registry:
            with SessionLocal() as db:
                seed_source_registry(db)
        if settings.auto_seed and settings.app_env == "development":
            with SessionLocal() as db:
                seed_sample_data(db)
        scheduler = None
        if settings.enable_scheduler:
            from app.workers.scheduler import build_scheduler

            scheduler = build_scheduler(SessionLocal)
            scheduler.start()
        yield
        if scheduler is not None:
            scheduler.shutdown(wait=False)

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

    # Configure rate limiting (simple in-memory limiter raises HTTPException(429) directly)
    from app.core.rate_limit import get_rate_limiter

    limiter = get_rate_limiter()
    if limiter:
        app.state.limiter = limiter

    # Configure request size limits
    app.add_middleware(
        RequestSizeLimitMiddleware,
        max_size=settings.max_request_size,
    )

    origins = _validate_cors_origins(settings.cors_origins, settings.app_env)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIdMiddleware)
    app.include_router(router)
    return app


app = create_app()
