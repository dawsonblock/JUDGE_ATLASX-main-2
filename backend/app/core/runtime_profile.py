from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeProfilePolicy:
    name: str
    production_ready_may_be_true: bool
    requires_evidence_store: bool
    requires_redis: bool
    requires_postgis_database: bool
    allows_inprocess_queue: bool
    allows_memory_rate_limit: bool
    allows_experimental_live_map: bool
    allows_workflow_admin: bool


_RUNTIME_POLICIES: dict[str, RuntimeProfilePolicy] = {
    "development": RuntimeProfilePolicy(
        name="development",
        production_ready_may_be_true=False,
        requires_evidence_store=False,
        requires_redis=False,
        requires_postgis_database=False,
        allows_inprocess_queue=True,
        allows_memory_rate_limit=True,
        allows_experimental_live_map=False,
        allows_workflow_admin=False,
    ),
    "alpha_local": RuntimeProfilePolicy(
        name="alpha_local",
        production_ready_may_be_true=False,
        requires_evidence_store=True,
        requires_redis=False,
        requires_postgis_database=False,
        allows_inprocess_queue=True,
        allows_memory_rate_limit=True,
        allows_experimental_live_map=False,
        allows_workflow_admin=False,
    ),
    "alpha_docker": RuntimeProfilePolicy(
        name="alpha_docker",
        production_ready_may_be_true=False,
        requires_evidence_store=True,
        requires_redis=True,
        requires_postgis_database=True,
        allows_inprocess_queue=False,
        allows_memory_rate_limit=False,
        allows_experimental_live_map=False,
        allows_workflow_admin=False,
    ),
    "staging": RuntimeProfilePolicy(
        name="staging",
        production_ready_may_be_true=False,
        requires_evidence_store=True,
        requires_redis=True,
        requires_postgis_database=True,
        allows_inprocess_queue=False,
        allows_memory_rate_limit=False,
        allows_experimental_live_map=False,
        allows_workflow_admin=False,
    ),
    "production": RuntimeProfilePolicy(
        name="production",
        production_ready_may_be_true=True,
        requires_evidence_store=True,
        requires_redis=True,
        requires_postgis_database=True,
        allows_inprocess_queue=False,
        allows_memory_rate_limit=False,
        allows_experimental_live_map=False,
        allows_workflow_admin=False,
    ),
    "test": RuntimeProfilePolicy(
        name="test",
        production_ready_may_be_true=False,
        requires_evidence_store=False,
        requires_redis=False,
        requires_postgis_database=False,
        allows_inprocess_queue=True,
        allows_memory_rate_limit=True,
        allows_experimental_live_map=False,
        allows_workflow_admin=True,
    ),
}


def resolve_runtime_profile(settings) -> RuntimeProfilePolicy:
    raw_profile = (getattr(settings, "runtime_profile", "") or "").strip().lower()
    if raw_profile in _RUNTIME_POLICIES:
        return _RUNTIME_POLICIES[raw_profile]

    app_env = (getattr(settings, "app_env", "") or "").strip().lower()
    if app_env in _RUNTIME_POLICIES:
        return _RUNTIME_POLICIES[app_env]

    if app_env == "production":
        return _RUNTIME_POLICIES["production"]
    if app_env == "staging":
        return _RUNTIME_POLICIES["staging"]
    if app_env == "test":
        return _RUNTIME_POLICIES["test"]
    return _RUNTIME_POLICIES["development"]


def validate_runtime_profile(settings, profile: RuntimeProfilePolicy) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    database_url = str(getattr(settings, "database_url", "") or "").lower()
    queue_backend = str(getattr(settings, "ingestion_queue_backend", "inprocess") or "inprocess")
    rate_limit_backend = str(getattr(settings, "rate_limit_backend", "memory") or "memory")
    redis_url = str(getattr(settings, "redis_url", "") or "")
    evidence_store_required = bool(getattr(settings, "evidence_store_required", False))
    evidence_store_root = str(getattr(settings, "evidence_store_root", "") or "")

    if profile.requires_evidence_store and not evidence_store_required:
        if profile.name == "production":
            errors.append("runtime_profile_violation:evidence_store_required=false")
        else:
            warnings.append(
                "runtime_profile_warning:evidence_store_required=false "
                f"for profile={profile.name}"
            )

    if profile.requires_evidence_store and not evidence_store_root:
        warnings.append(
            "runtime_profile_warning:evidence_store_root_missing "
            f"for profile={profile.name}"
        )

    if profile.requires_redis and not redis_url:
        if profile.name in {"staging", "production"}:
            errors.append("runtime_profile_violation:redis_required_but_missing")
        else:
            warnings.append(
                "runtime_profile_warning:redis_required_but_missing "
                f"for profile={profile.name}"
            )

    if not profile.allows_inprocess_queue and queue_backend == "inprocess":
        if profile.name in {"staging", "production", "alpha_docker"}:
            errors.append(
                "runtime_profile_violation:inprocess_queue_not_allowed"
                f":profile={profile.name}"
            )

    if not profile.allows_memory_rate_limit and rate_limit_backend == "memory":
        if profile.name in {"staging", "production", "alpha_docker"}:
            errors.append(
                "runtime_profile_violation:memory_rate_limit_not_allowed"
                f":profile={profile.name}"
            )

    if profile.requires_postgis_database and "postgresql" not in database_url:
        if profile.name in {"staging", "production", "alpha_docker"}:
            errors.append(
                "runtime_profile_violation:postgresql_required"
                f":profile={profile.name}"
            )

    if not profile.allows_experimental_live_map and bool(
        getattr(settings, "enable_experimental_live_map", False)
    ):
        errors.append(
            "runtime_profile_violation:experimental_live_map_not_allowed"
            f":profile={profile.name}"
        )

    if not profile.allows_workflow_admin and bool(
        getattr(settings, "enable_workflow_admin", False)
    ):
        errors.append(
            "runtime_profile_violation:workflow_admin_not_allowed"
            f":profile={profile.name}"
        )

    return errors, warnings
