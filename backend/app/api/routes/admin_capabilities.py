"""Admin feature capability flags for frontend/backend alignment."""

from fastapi import APIRouter, Depends

from app.auth.actor import AdminActor
from app.core.config import get_settings
from app.security.import_authority import require_source_admin_actor

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/capabilities")
def admin_capabilities(
    actor: AdminActor = Depends(require_source_admin_actor),
) -> dict[str, bool]:
    settings = get_settings()
    return {
        "workflow_admin": bool(settings.enable_workflow_admin),
        "experimental_live_map": bool(settings.enable_experimental_live_map),
        "source_registry": True,
        "review_queue": True,
        "memory_admin": True,
    }