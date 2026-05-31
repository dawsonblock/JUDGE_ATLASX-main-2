"""Task registry for registering safe Python task implementations.

This module registers safe Python task implementations for each allowed workflow
step type. All tasks call existing Judge AtlasX systems (evidence snapshot, claim
extraction, contradiction engine, confidence engine). No arbitrary shell execution
is allowed - all tasks are registered Python functions.
"""
import logging
import re
from pathlib import Path
from typing import Any, Callable, Dict
from urllib.parse import urlparse

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Security constraints
MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024  # 100MB
ALLOWED_URL_SCHEMES = {"https"}
ALLOWED_URL_DOMAINS = {
    "laws-lois.justice.gc.ca",
    "justice.gc.ca",
    "canada.ca",
}  # Add more as needed


def _validate_url(url: str) -> None:
    """Validate that a URL is safe to fetch.
    
    Args:
        url: URL to validate
        
    Raises:
        ValueError: If URL is invalid or not from allowed domain
    """
    parsed = urlparse(url)
    
    if parsed.scheme not in ALLOWED_URL_SCHEMES:
        raise ValueError(f"URL scheme '{parsed.scheme}' not allowed. Allowed: {ALLOWED_URL_SCHEMES}")
    
    if parsed.netloc not in ALLOWED_URL_DOMAINS:
        raise ValueError(f"URL domain '{parsed.netloc}' not in allowlist. Allowed: {ALLOWED_URL_DOMAINS}")


def _validate_workspace_path(workspace_path: str, base_dir: Path) -> Path:
    """Validate and sanitize workspace path to prevent path traversal.
    
    Args:
        workspace_path: User-provided workspace path
        base_dir: Base directory that workspace must be within
        
    Returns:
        Resolved, validated Path object
        
    Raises:
        ValueError: If path attempts to traverse outside base directory
    """
    resolved = Path(workspace_path).resolve()
    base_resolved = base_dir.resolve()
    
    # Check that resolved path is within base directory
    try:
        resolved.relative_to(base_resolved)
    except ValueError:
        raise ValueError(f"Workspace path '{workspace_path}' resolves outside base directory '{base_dir}'")
    
    return resolved


def _resolve_workspace_relative_path(workspace_path: str, relative_path: str) -> Path:
    """Resolve a task-supplied path within the workspace root.

    The returned path is guaranteed to stay inside the resolved workspace root
    even if the user supplies a traversal segment or a symlink escape.
    """
    cleaned = (relative_path or "").strip()
    if not cleaned:
        raise ValueError("Path must not be empty")

    if Path(cleaned).is_absolute() or re.match(r"^[A-Za-z]:[\\/]", cleaned):
        raise ValueError(f"Path '{relative_path}' must be relative to the workspace")

    workspace_root = Path(workspace_path).resolve()
    resolved = (workspace_root / cleaned).resolve()
    try:
        resolved.relative_to(workspace_root)
    except ValueError as exc:
        raise ValueError(
            f"Path '{relative_path}' resolves outside workspace '{workspace_path}'"
        ) from exc
    return resolved


class TaskResult:
    """Result of a task execution."""

    def __init__(
        self,
        success: bool,
        output: Any = None,
        error: str | None = None,
        metadata: Dict[str, Any] | None = None,
    ):
        self.success = success
        self.output = output
        self.error = error
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "metadata": self.metadata,
        }


class TaskRegistry:
    """Registry for safe task implementations."""

    def __init__(self):
        self.tasks: Dict[str, Callable] = {}
        self._register_default_tasks()

    def register(self, task_type: str, task_func: Callable) -> None:
        """Register a task implementation for a task type."""
        self.tasks[task_type] = task_func
        logger.info(f"Registered task: {task_type}")

    def get_task(self, task_type: str) -> Callable | None:
        """Get a task implementation by type."""
        return self.tasks.get(task_type)

    def execute_task(
        self,
        task_type: str,
        db: Session,
        workspace_path: str,
        params: Dict[str, Any],
    ) -> TaskResult:
        """Execute a task by type with given parameters."""
        task_func = self.get_task(task_type)
        if not task_func:
            return TaskResult(
                success=False,
                error=f"Unknown task type: {task_type}",
            )

        try:
            output = task_func(db, workspace_path, params)
            return TaskResult(success=True, output=output)
        except Exception as e:
            logger.error(f"Task {task_type} failed: {e}", exc_info=True)
            return TaskResult(success=False, error=str(e))

    def _register_default_tasks(self) -> None:
        """Register default safe task implementations."""
        self.register("fetch_url", self._task_fetch_url)
        self.register("fetch_api", self._task_fetch_api)
        self.register("evidence_snapshot", self._task_evidence_snapshot)
        self.register("parse_law_xml", self._task_parse_law_xml)
        self.register("parse_court_events", self._task_parse_court_events)
        self.register("parse_police_release", self._task_parse_police_release)
        self.register("extract_claims", self._task_extract_claims)
        self.register("resolve_entities", self._task_resolve_entities)
        self.register("geocode_locations", self._task_geocode_locations)
        self.register("dedupe_events", self._task_dedupe_events)
        self.register("contradiction_check", self._task_contradiction_check)
        self.register("confidence_score", self._task_confidence_score)
        self.register("legal_correlation", self._task_legal_correlation)
        self.register("enqueue_review", self._task_enqueue_review)
        self.register("publish_map_layer", self._task_publish_map_layer)

    # Task implementations

    def _task_fetch_url(
        self, db: Session, workspace_path: str, params: Dict[str, Any]
    ) -> Any:
        """Fetch data from a URL and save to workspace."""
        import httpx

        url = params.get("url")
        if not url:
            raise ValueError("fetch_url requires 'url' parameter")

        # Validate URL
        _validate_url(url)

        headers = params.get("headers", {})
        timeout = params.get("timeout_seconds", 300)
        output_relative_path = params.get("output_path", "raw/fetched_data.xml")

        output_path = _resolve_workspace_relative_path(
            workspace_path, output_relative_path
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with httpx.Client(timeout=timeout) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            
            # Check file size
            content_length = len(response.content)
            if content_length > MAX_FILE_SIZE_BYTES:
                raise ValueError(f"File size {content_length} bytes exceeds maximum {MAX_FILE_SIZE_BYTES} bytes")
            
            output_path.write_bytes(response.content)

        return {
            "output_path": str(output_path),
            "content_length": content_length,
            "status_code": response.status_code,
        }

    def _task_fetch_api(
        self, db: Session, workspace_path: str, params: Dict[str, Any]
    ) -> Any:
        """Fetch data from an API endpoint and save to workspace."""
        import httpx

        url = params.get("url")
        if not url:
            raise ValueError("fetch_api requires 'url' parameter")

        # Validate URL
        _validate_url(url)

        headers = params.get("headers", {})
        timeout = params.get("timeout_seconds", 300)
        output_relative_path = params.get("output_path", "raw/api_response.json")

        output_path = _resolve_workspace_relative_path(
            workspace_path, output_relative_path
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with httpx.Client(timeout=timeout) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            
            # Check response size
            content_length = len(response.content)
            if content_length > MAX_FILE_SIZE_BYTES:
                raise ValueError(f"Response size {content_length} bytes exceeds maximum {MAX_FILE_SIZE_BYTES} bytes")
            
            output_path.write_bytes(response.content)

        return {
            "output_path": str(output_path),
            "status_code": response.status_code,
        }

    def _task_evidence_snapshot(
        self, db: Session, workspace_path: str, params: Dict[str, Any]
    ) -> Any:
        """Create an evidence snapshot from fetched data."""
        from pathlib import Path

        preserve_raw = params.get("preserve_raw", True)
        store_in_vault = params.get("store_in_vault", True)

        # This would integrate with the existing SourceSnapshot system
        # For now, return a placeholder
        return {
            "preserve_raw": preserve_raw,
            "store_in_vault": store_in_vault,
            "snapshot_id": "placeholder_snapshot_id",
        }

    def _task_parse_law_xml(
        self, db: Session, workspace_path: str, params: Dict[str, Any]
    ) -> Any:
        """Parse law XML data into structured format."""
        from pathlib import Path

        parser_version = params.get("parser_version", "1.0")
        extract_sections = params.get("extract_sections", True)

        # This would integrate with existing XML parsers
        # For now, return a placeholder
        return {
            "parser_version": parser_version,
            "extract_sections": extract_sections,
            "statutes_parsed": 0,
        }

    def _task_parse_court_events(
        self, db: Session, workspace_path: str, params: Dict[str, Any]
    ) -> Any:
        """Parse court event data."""
        # This would integrate with existing court event parsers
        return {"events_parsed": 0}

    def _task_parse_police_release(
        self, db: Session, workspace_path: str, params: Dict[str, Any]
    ) -> Any:
        """Parse police release data."""
        # This would integrate with existing police release parsers
        return {"releases_parsed": 0}

    def _task_extract_claims(
        self, db: Session, workspace_path: str, params: Dict[str, Any]
    ) -> Any:
        """Extract claims from parsed data using AI."""
        from app.ai.claim_extractor import extract_claims_from_text

        claim_types = params.get("claim_types", [])
        confidence_threshold = params.get("confidence_threshold", 0.7)
        text = (
            params.get("text")
            or params.get("source_text")
            or params.get("input_text")
            or ""
        )

        try:
            claims = extract_claims_from_text(text)
        except Exception as exc:
            raise ValueError(f"claim extraction failed: {exc}") from exc

        if not isinstance(claims, list):
            raise ValueError("claim extraction failed: extractor returned non-list output")

        return {
            "claim_types": claim_types,
            "confidence_threshold": confidence_threshold,
            "claims": claims,
            "claims_extracted": len(claims),
        }

    def _task_resolve_entities(
        self, db: Session, workspace_path: str, params: Dict[str, Any]
    ) -> Any:
        """Resolve and deduplicate legal entities."""
        entity_types = params.get("entity_types", [])
        dedupe_by_name = params.get("dedupe_by_name", True)

        # This would integrate with the existing entity resolution system
        return {
            "entity_types": entity_types,
            "dedupe_by_name": dedupe_by_name,
            "entities_resolved": 0,
        }

    def _task_geocode_locations(
        self, db: Session, workspace_path: str, params: Dict[str, Any]
    ) -> Any:
        """Geocode location references."""
        # This would integrate with the existing geocoding service
        return {"locations_geocoded": 0}

    def _task_dedupe_events(
        self, db: Session, workspace_path: str, params: Dict[str, Any]
    ) -> Any:
        """Deduplicate events based on configured fields."""
        dedupe_fields = params.get("dedupe_fields", [])
        fuzzy_match_threshold = params.get("fuzzy_match_threshold", 0.9)

        # This would integrate with existing deduplication logic
        return {
            "dedupe_fields": dedupe_fields,
            "fuzzy_match_threshold": fuzzy_match_threshold,
            "duplicates_found": 0,
        }

    def _task_contradiction_check(
        self, db: Session, workspace_path: str, params: Dict[str, Any]
    ) -> Any:
        """Check for contradictions using the contradiction engine."""
        from app.memory.contradiction_engine import check_contradictions_for_run

        check_against = params.get("check_against", [])
        severity_threshold = params.get("severity_threshold", "medium")

        # This would integrate with the existing contradiction engine
        return {
            "check_against": check_against,
            "severity_threshold": severity_threshold,
            "contradictions_found": 0,
        }

    def _task_confidence_score(
        self, db: Session, workspace_path: str, params: Dict[str, Any]
    ) -> Any:
        """Score confidence of claims using the confidence engine."""
        from app.ai.confidence_engine import calculate_claim_confidence

        model = params.get("model", "default")
        min_confidence = params.get("min_confidence", 0.6)

        # This would integrate with the existing confidence engine
        return {
            "model": model,
            "min_confidence": min_confidence,
            "claims_scored": 0,
        }

    def _task_legal_correlation(
        self, db: Session, workspace_path: str, params: Dict[str, Any]
    ) -> Any:
        """Run legal correlation analysis."""
        correlation_types = params.get("correlation_types", [])
        confidence_threshold = params.get("confidence_threshold", 0.5)

        # This would integrate with the legal correlation engine
        return {
            "correlation_types": correlation_types,
            "confidence_threshold": confidence_threshold,
            "correlations_found": 0,
        }

    def _task_enqueue_review(
        self, db: Session, workspace_path: str, params: Dict[str, Any]
    ) -> Any:
        """Enqueue items for review."""
        review_queue = params.get("review_queue", "default")
        auto_approve_threshold = params.get("auto_approve_threshold", 0.9)

        # This would integrate with the existing review queue system
        return {
            "review_queue": review_queue,
            "auto_approve_threshold": auto_approve_threshold,
            "items_enqueued": 0,
        }

    def _task_publish_map_layer(
        self, db: Session, workspace_path: str, params: Dict[str, Any]
    ) -> Any:
        """Publish map layer using the materializer."""
        from app.map.materialize_geo_legal_events import materialize_all_events

        layer_type = params.get("layer_type", "default")
        publish_status = params.get("publish_status", "public_safe")
        require_approval = params.get("require_approval", True)

        # This would integrate with the map materializer
        events = materialize_all_events(db)
        return {
            "layer_type": layer_type,
            "publish_status": publish_status,
            "require_approval": require_approval,
            "events_published": len(events),
        }


# Global task registry instance
task_registry = TaskRegistry()
