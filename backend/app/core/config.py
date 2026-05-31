from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "JudgeTracker Atlas"
    database_url: str = "sqlite:///./judgetracker.db"
    courtlistener_api_token: str | None = None
    courtlistener_base_url: str = "https://www.courtlistener.com/api/rest/v4"
    courtlistener_max_pages: int = 10
    courtlistener_max_dockets_per_run: int = 100
    courtlistener_timeout_seconds: int = 60
    app_env: str = "development"
    runtime_profile: Literal[
        "development",
        "alpha_local",
        "alpha_docker",
        "staging",
        "production",
        "test",
    ] = "development"
    auto_seed: bool = False
    # Independent gate for source registry seeding (prod-safe, defaults True)
    seed_source_registry: bool = True
    cors_origins: str = "https://localhost:3000"
    enable_admin_imports: bool = False
    enable_admin_review: bool = False
    enable_public_event_post: bool = False
    admin_token: str | None = None
    admin_review_token: str | None = None
    geonames_username: str | None = None
    statscan_enabled: bool = False
    fbi_crime_enabled: bool = False
    local_feeds_enabled: bool = False
    gdelt_enabled: bool = False
    # Legacy U.S.-centric ingestion surfaces (GDELT/Chicago/Toronto/LA/FBI/
    # CourtListener bulk). Keep disabled by default for Canada-first alpha.
    courtlistener_bulk_data_dir: str = "data/courtlistener-bulk"
    courtlistener_bulk_snapshot_date: str | None = None
    courtlistener_bulk_enabled_files: str = (
        "courts,people-db-people,people-db-positions,dockets,opinion-clusters"
    )
    courtlistener_bulk_import_batch_size: int = 500
    courtlistener_bulk_normalize_batch_size: int = 200
    courtlistener_bulk_include_opinions: bool = False
    ollama_enabled: bool = False
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "mistral"
    ollama_timeout_seconds: int = 30

    # Semantic embeddings (sentence-transformers); disabled by default so the
    # heavy torch dependency is never loaded in production unless opted in.
    embeddings_enabled: bool = False
    embeddings_model: str = "all-MiniLM-L6-v2"
    embeddings_similarity_threshold: float = 0.70
    embeddings_top_k: int = 5

    # Rate limiting (requests per minute)
    rate_limit_public: int = 100  # Public API endpoints
    rate_limit_admin: int = 30  # Admin API endpoints
    rate_limit_map: int = 60  # Map endpoints
    rate_limit_ingestion: int = 10  # Ingestion endpoints
    rate_limit_enabled: bool = True
    # "memory" or "redis" - default to redis for production
    rate_limit_backend: str = "redis"
    redis_url: str | None = None
    # Comma-separated list of trusted proxy IPs
    trusted_proxy_ips: str = ""

    # Evidence store configuration
    evidence_store_root: str | None = None
    evidence_store_required: bool = False
    evidence_store_probe_write: bool = True

    # Object storage configuration
    storage_backend: str = "local"  # "local", "minio", "azure_blob"
    storage_local_path: str = "./storage"  # For local backend

    # Request size limits (bytes)
    max_request_size: int = 10 * 1024 * 1024  # 10MB for regular API
    max_csv_upload_size: int = 50 * 1024 * 1024  # 50MB for CSV uploads
    # Row-count hard cap for CSV ingestion (independent of byte limit)
    max_csv_rows: int = 1_000_000

    # JWT authentication
    jwt_secret_key: str = "CHANGE-ME-BEFORE-PRODUCTION"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    # Set to True once at least one admin user has been created
    # via POST /api/auth/register
    jwt_auth_enabled: bool = False
    # Secret required for first-admin bootstrap in non-development environments
    first_admin_secret: str | None = None  # JTA_FIRST_ADMIN_SECRET

    # Legacy shared-token admin compatibility.
    # DEPRECATED — disabled by default.
    # Set to True only for local development.
    # Never enable in production. Startup emits a warning when True.
    enable_legacy_admin_token: bool = False

    # Legacy U.S. ingestion routes (GDELT, Chicago, LA, FBI,
    # CourtListener bulk, Toronto, StatsCan).
    # Disabled by default as part of Canada-first strategy.
    # Set JTA_ENABLE_LEGACY_US_INGEST_ROUTES=true
    # to mount admin_legacy_ingest router.
    enable_legacy_us_ingest_routes: bool = False

    # Experimental live-map public router remains blocked by default.
    enable_experimental_live_map: bool = False
    # Public-platform endpoints and UI surfaces from feasibility donor code.
    # Must remain disabled by default until all hardening gates are complete.
    enable_public_platform: bool = False
    # Workflow admin router remains blocked by default.
    enable_workflow_admin: bool = False
    public_map_min_confidence: float = 0.65

    # Enforce JWT-only authority for mutation routes
    # (review decisions, source configuration updates,
    # enable/disable, and manual source runs).
    # When True, shared-token actors are rejected for mutation operations.
    # Default: True (JWT-only by default;
    # set False only for legacy compatibility)
    enforce_jwt_mutations: bool = True

    # Background scheduler (APScheduler); disabled by default for safe deploys
    enable_scheduler: bool = False

    # Ingestion queue backend selection: "inprocess" or "postgres".
    # inprocess is alpha-only and not production-capable.
    # postgres is alpha-hardened with worker-safe features but not
    # production-certified.
    ingestion_queue_backend: Literal["inprocess", "postgres"] = "inprocess"

    # Allow alpha postgres queue in production environments.
    # When False, postgres queue is blocked in production.
    # When True, postgres queue is allowed with explicit override.
    # Default: False (production-safe default).
    # Rules: local/dev allowed, test allowed, production blocked unless True.
    allow_alpha_postgres_queue: bool = False

    # Relationship arc publication policy
    # Disabled by default — arcs require manual review
    # and policy sign-off before being published.
    # See backend/app/policies/relationship_arc_policy.py.
    enable_public_relationship_arcs: bool = False
    # Minimum number of evidence references an edge must carry to be published.
    public_relationship_arc_min_evidence: int = 2
    # Hard cap on public arc results per request.
    public_relationship_arc_max_results: int = 250

    # Canadian case law (CanLII REST API v1)
    canlii_api_key: str | None = None

    # Lexum SCC bulk API key (for historical SCC decision back-fill)
    # Set JTA_LEXUM_API_KEY or LEXUM_API_KEY in environment
    lexum_api_key: str | None = None

    # Justice Canada XML law targets (comma-separated unique IDs).
    # Keep defaults intentionally narrow for development and proof runs.
    laws_xml_target_ids: str = "C-46"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="JTA_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
