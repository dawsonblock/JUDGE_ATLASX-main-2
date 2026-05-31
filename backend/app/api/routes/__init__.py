from app.api.routes import (
    admin_capabilities,
    admin_ingest,
    admin_ingestion,
    admin_ingestion_jobs,
    admin_legacy_ingest,
    admin_live_map,
    admin_memory,
    admin_quarantine,
    admin_review,
    admin_sources,
    ai_correctness,
    ai_review,
    auth,
    boundaries,
    chat,
    evidence,
    evidence_store,
    graph,
    ingestion,
    live_map,
    map,
    map_record,
    public_events,
    snapshots,
    sources,
    status,
    workflow_admin,
)
from app.core.config import get_settings
from app.serializers.public import is_mappable as _is_mappable
from fastapi import APIRouter

router = APIRouter()
router.include_router(auth.router)
router.include_router(public_events.router)
settings = get_settings()
if settings.enable_experimental_live_map:
    router.include_router(live_map.router)
router.include_router(map.router)
router.include_router(map_record.router)
router.include_router(boundaries.router)
router.include_router(ingestion.router)
router.include_router(ai_review.router)
router.include_router(admin_review.router)
router.include_router(admin_ingest.router)
router.include_router(admin_ingestion.router)
router.include_router(admin_ingestion_jobs.router)
router.include_router(admin_quarantine.router)
router.include_router(admin_sources.router)
router.include_router(admin_memory.router)
router.include_router(admin_live_map.router)
router.include_router(admin_capabilities.router)
router.include_router(chat.router)
router.include_router(evidence_store.router)
router.include_router(graph.router)
router.include_router(evidence.router)
router.include_router(snapshots.router)
router.include_router(ai_correctness.router)
router.include_router(sources.router)
if settings.enable_workflow_admin:
    router.include_router(workflow_admin.router)
router.include_router(status.router)

# Conditionally mount legacy U.S. ingestion routes (disabled by default)
if settings.enable_legacy_us_ingest_routes:
    router.include_router(admin_legacy_ingest.router)

__all__ = ["router", "_is_mappable"]
