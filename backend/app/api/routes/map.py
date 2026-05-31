from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings, get_settings
from app.core.rate_limit import rate_limit_map
from app.db.session import get_db
from app.policies.relationship_arc_policy import evaluate_arc_request
from app.policies.publication_policy import can_show_public_entity
from app.models.entities import (
    Court,
    CrimeIncident,
    CrimeIncidentSource,
    EntityGraphEdge,
    Judge,
    LegalSource,
    Location,
)
from app.serializers.public import (
    crime_incident_to_geojson_feature,
    event_to_geojson_feature,
    filtered_events_query,
    is_public_crime_incident_mappable,
)
from app.services.constants import PUBLIC_REVIEW_STATUSES
from app.services.publish_rules import UNSAFE_MAP_PRECISIONS

router = APIRouter()

PLATFORM_DISCLAIMER = (
    "JudgeTracker Atlas is a hardened prototype. All records enter a review workflow "
    "before public display. Pending, rejected, and removed records are excluded. "
    "This is not a substitute for legal advice."
)


# Maximum bbox area (degrees² longitude × latitude) accepted per request.
# 25° × 25° = 625 sq degrees — covers most single-country views.
_MAX_BBOX_AREA_SQ_DEG = 625.0
_LEGACY_QUARANTINED_CATEGORIES = {"corruption", "misconduct"}


def _parse_bbox(
    bbox: str | None,
    max_area: float | None = _MAX_BBOX_AREA_SQ_DEG,
) -> tuple[float, float, float, float] | None:
    """Parse 'west,south,east,north' bbox string. Returns None if not provided.

    max_area: if set, rejects bboxes larger than this many sq degrees.  Pass
    ``None`` to disable the area cap (e.g. for public-event queries that are
    not privacy-sensitive).
    """
    if not bbox:
        return None
    parts = bbox.split(",")
    if len(parts) != 4:
        raise HTTPException(
            status_code=422, detail="bbox must be 'west,south,east,north'"
        )
    try:
        west, south, east, north = (float(p.strip()) for p in parts)
    except ValueError:
        raise HTTPException(status_code=422, detail="bbox values must be numeric")
    if not (
        -180 <= west <= 180
        and -180 <= east <= 180
        and -90 <= south <= 90
        and -90 <= north <= 90
    ):
        raise HTTPException(
            status_code=422, detail="bbox values out of valid WGS84 range"
        )
    if south > north:
        raise HTTPException(status_code=422, detail="bbox south must be <= north")
    if west > east:
        raise HTTPException(
            status_code=422,
            detail="bbox west must be <= east (antimeridian crossing not supported)",
        )
    if max_area is not None:
        area = (east - west) * (north - south)
        if area > max_area:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"bbox area ({area:.1f} sq degrees) exceeds maximum "
                    f"{max_area:.0f} sq degrees per request"
                ),
            )
    return west, south, east, north


def _is_postgres(db: Session) -> bool:
    """Check if database is PostgreSQL (for PostGIS support)."""
    dialect_name = db.bind.dialect.name if db.bind else ""
    return dialect_name == "postgresql"


def _apply_bbox_filter_location(
    stmt, bbox_parsed: tuple[float, float, float, float] | None, db: Session
):
    """Apply bbox filter using lat/lon comparisons only.

    NOTE: Location.geom is not used for bbox filtering because it can be NULL
    for rows inserted after the migration. Until geom is trigger-maintained or
    a generated column, bbox filtering uses only latitude/longitude columns.
    """
    if not bbox_parsed:
        return stmt
    west, south, east, north = bbox_parsed
    # Always use lat/lon comparisons - geom column is not yet trustworthy
    stmt = stmt.where(
        Location.longitude >= west,
        Location.longitude <= east,
        Location.latitude >= south,
        Location.latitude <= north,
    )
    return stmt


@router.get("/api/map/events", dependencies=[Depends(rate_limit_map)])
def map_events(
    start: date | None = None,
    end: date | None = None,
    court_id: int | None = None,
    judge_id: int | None = None,
    event_type: str | None = None,
    repeat_offender_indicator: bool | None = None,
    repeat_offender: bool | None = None,
    verified_only: bool = False,
    source_type: str | None = None,
    official_only: bool | None = Query(
        None,
        description=(
            "True = restrict to official government/court sources only "
            "(source_type in court_records, government_data, official_government_open_data). "
            "False = exclude official sources. None = no filter."
        ),
    ),
    bbox: str | None = Query(
        None, description="west,south,east,north in WGS84 decimal degrees"
    ),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    indicator_filter = (
        repeat_offender_indicator
        if repeat_offender_indicator is not None
        else repeat_offender
    )
    # map_events returns public court records — no privacy-based area cap needed.
    bbox_parsed = _parse_bbox(bbox, max_area=None)
    stmt = filtered_events_query(
        start,
        end,
        court_id,
        judge_id,
        event_type,
        indicator_filter,
        verified_only,
        source_type,
        limit + 1,
        offset,
    )
    _OFFICIAL_SOURCE_TYPES = (
        "court_records",
        "government_data",
        "official_government_open_data",
    )
    if official_only is True and not source_type:
        from app.models.entities import (  # local to avoid circular
            Event as _Ev,
            EventSource as _EvSrc,
        )
        stmt = (
            stmt.join(_EvSrc, _EvSrc.event_id == _Ev.id, isouter=False)
            .join(LegalSource, LegalSource.id == _EvSrc.source_id, isouter=False)
            .where(LegalSource.source_type.in_(_OFFICIAL_SOURCE_TYPES))
        )
    elif official_only is False and not source_type:
        from app.models.entities import Event as _Ev, EventSource as _EvSrc
        stmt = (
            stmt.join(_EvSrc, _EvSrc.event_id == _Ev.id, isouter=False)
            .join(LegalSource, LegalSource.id == _EvSrc.source_id, isouter=False)
            .where(LegalSource.source_type.not_in(_OFFICIAL_SOURCE_TYPES))
        )
    stmt = stmt.where(
        Location.location_type.not_in(["court_placeholder", "unmapped_court"]),
        Location.latitude.is_not(None),
        Location.longitude.is_not(None),
        Location.latitude != 0.0,
        Location.longitude != 0.0,
    )
    stmt = _apply_bbox_filter_location(stmt, bbox_parsed, db)
    rows = db.scalars(stmt).unique().all()
    truncated = len(rows) > limit
    events = rows[:limit]
    filters_applied: dict = {
        "public_visibility": True,
        "review_status": list(PUBLIC_REVIEW_STATUSES),
    }
    if start:
        filters_applied["start"] = start.isoformat()
    if end:
        filters_applied["end"] = end.isoformat()
    if court_id:
        filters_applied["court_id"] = court_id
    if judge_id:
        filters_applied["judge_id"] = judge_id
    if event_type:
        filters_applied["event_type"] = event_type
    if indicator_filter is not None:
        filters_applied["repeat_offender_indicator"] = indicator_filter
    if verified_only:
        filters_applied["verified_only"] = True
    if source_type:
        filters_applied["source_type"] = source_type
    if official_only is not None:
        filters_applied["official_only"] = official_only
    if bbox_parsed:
        filters_applied["bbox"] = bbox
    return {
        "type": "FeatureCollection",
        "returned_count": len(events),
        "truncated": truncated,
        "filters_applied": filters_applied,
        "disclaimer": PLATFORM_DISCLAIMER,
        "features": [event_to_geojson_feature(event) for event in events],
    }


@router.get("/api/map/crime-incidents", dependencies=[Depends(rate_limit_map)])
def map_crime_incidents(
    is_public: bool = Query(True, description="Must be true for public incident map data"),
    reviewed_only: bool = Query(True, description="Must be true to require reviewed records"),
    start: datetime | None = None,
    end: datetime | None = None,
    city: str | None = None,
    province_state: str | None = None,
    country: str | None = None,
    jurisdiction: str | None = Query(
        None, description="Filter by Canadian province code (e.g., ON, QC)"
    ),
    start_date: str | None = Query(None, description="Filter by start date (YYYY-MM-DD)"),
    end_date: str | None = Query(None, description="Filter by end date (YYYY-MM-DD)"),
    incident_category: str | None = None,
    verification_status: str | None = None,
    source_name: str | None = None,
    aggregate_only: bool | None = Query(None, description="True = aggregate stats only"),
    exclude_aggregate: bool | None = Query(
        True,
        description="True = exclude aggregate stats",
    ),
    last_hours: int | None = Query(None, ge=1, le=24 * 365),
    bbox: str | None = Query(
        None, description="west,south,east,north in WGS84 decimal degrees"
    ),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    if not is_public:
        raise HTTPException(status_code=422, detail="is_public must be true")
    if not reviewed_only:
        raise HTTPException(status_code=422, detail="reviewed_only must be true")

    bbox_parsed = _parse_bbox(bbox)
    stmt = (
        select(CrimeIncident)
        .options(
            selectinload(CrimeIncident.source_links).selectinload(
                CrimeIncidentSource.source
            ),
            selectinload(CrimeIncident.event_links),
        )
        .where(
            CrimeIncident.is_public.is_(True),
            CrimeIncident.review_status.in_(PUBLIC_REVIEW_STATUSES),
            CrimeIncident.latitude_public.is_not(None),
            CrimeIncident.longitude_public.is_not(None),
            CrimeIncident.latitude_public != 0.0,
            CrimeIncident.longitude_public != 0.0,
            CrimeIncident.precision_level.not_in(UNSAFE_MAP_PRECISIONS),
        )
    )
    if start:
        stmt = stmt.where(CrimeIncident.reported_at >= start)
    if end:
        stmt = stmt.where(CrimeIncident.reported_at <= end)
    if jurisdiction:
        stmt = stmt.where(CrimeIncident.jurisdiction == jurisdiction)
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date)
            stmt = stmt.where(CrimeIncident.reported_at >= start_dt)
        except ValueError:
            raise HTTPException(status_code=422, detail="start_date must be YYYY-MM-DD format")
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date)
            stmt = stmt.where(CrimeIncident.reported_at <= end_dt)
        except ValueError:
            raise HTTPException(status_code=422, detail="end_date must be YYYY-MM-DD format")
    if last_hours:
        stmt = stmt.where(
            CrimeIncident.reported_at
            >= datetime.now(timezone.utc) - timedelta(hours=last_hours)
        )
    if city:
        stmt = stmt.where(CrimeIncident.city == city)
    if province_state:
        stmt = stmt.where(CrimeIncident.province_state == province_state)
    if country:
        stmt = stmt.where(CrimeIncident.country == country)
    if incident_category:
        if incident_category in _LEGACY_QUARANTINED_CATEGORIES:
            raise HTTPException(
                status_code=422,
                detail=(
                    "incident_category is quarantined from public filters; "
                    "use approved category taxonomy"
                ),
            )
        stmt = stmt.where(CrimeIncident.incident_category == incident_category)
    if verification_status:
        stmt = stmt.where(CrimeIncident.verification_status == verification_status)
    if source_name:
        stmt = stmt.where(CrimeIncident.source_name == source_name)
    if aggregate_only is True:
        stmt = stmt.where(CrimeIncident.is_aggregate.is_(True))
    elif exclude_aggregate is True:
        stmt = stmt.where(CrimeIncident.is_aggregate.is_(False))
    if bbox_parsed:
        west, south, east, north = bbox_parsed
        # CrimeIncident doesn't have geom column yet, use lat/lon fallback
        stmt = stmt.where(
            CrimeIncident.longitude_public >= west,
            CrimeIncident.longitude_public <= east,
            CrimeIncident.latitude_public >= south,
            CrimeIncident.latitude_public <= north,
        )
    stmt = (
        stmt.order_by(
            CrimeIncident.reported_at.desc().nullslast(), CrimeIncident.id.desc()
        )
        .offset(offset)
        .limit(limit + 1)
    )
    rows = db.scalars(stmt).all()
    truncated = len(rows) > limit
    incidents = [
        r
        for r in rows[:limit]
        if is_public_crime_incident_mappable(r)
        and can_show_public_entity(db, "crime_incident", r).allowed
    ]
    filters_applied: dict = {
        "is_public": True,
        "review_status": list(PUBLIC_REVIEW_STATUSES),
        "reviewed_only": reviewed_only,
    }
    if city:
        filters_applied["city"] = city
    if incident_category:
        filters_applied["incident_category"] = incident_category
    if aggregate_only is True:
        filters_applied["aggregate_only"] = True
    elif exclude_aggregate is True:
        filters_applied["exclude_aggregate"] = True
    if bbox_parsed:
        filters_applied["bbox"] = bbox
    return {
        "type": "FeatureCollection",
        "returned_count": len(incidents),
        "truncated": truncated,
        "filters_applied": filters_applied,
        "disclaimer": PLATFORM_DISCLAIMER,
        "features": [
            crime_incident_to_geojson_feature(incident) for incident in incidents
        ],
    }


@router.get("/api/map/crime-aggregates", dependencies=[Depends(rate_limit_map)])
def map_crime_aggregates(
    start: datetime | None = None,
    end: datetime | None = None,
    city: str | None = None,
    province_state: str | None = None,
    country: str | None = None,
    incident_category: str | None = None,
    verification_status: str | None = None,
    source_name: str | None = None,
    last_hours: int | None = Query(None, ge=1, le=24 * 365),
    bbox: str | None = Query(
        None, description="west,south,east,north in WGS84 decimal degrees"
    ),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Fetch aggregate crime statistics only (separate from individual incidents)."""
    bbox_parsed = _parse_bbox(bbox)
    stmt = (
        select(CrimeIncident)
        .options(
            selectinload(CrimeIncident.source_links).selectinload(
                CrimeIncidentSource.source
            ),
            selectinload(CrimeIncident.event_links),
        )
        .where(
            CrimeIncident.is_public.is_(True),
            CrimeIncident.review_status.in_(PUBLIC_REVIEW_STATUSES),
            CrimeIncident.is_aggregate.is_(True),  # Only aggregates
            CrimeIncident.latitude_public.is_not(None),
            CrimeIncident.longitude_public.is_not(None),
            CrimeIncident.latitude_public != 0.0,
            CrimeIncident.longitude_public != 0.0,
            CrimeIncident.precision_level.not_in(UNSAFE_MAP_PRECISIONS),
        )
    )
    if start:
        stmt = stmt.where(CrimeIncident.reported_at >= start)
    if end:
        stmt = stmt.where(CrimeIncident.reported_at <= end)
    if last_hours:
        stmt = stmt.where(
            CrimeIncident.reported_at
            >= datetime.now(timezone.utc) - timedelta(hours=last_hours)
        )
    if city:
        stmt = stmt.where(CrimeIncident.city == city)
    if province_state:
        stmt = stmt.where(CrimeIncident.province_state == province_state)
    if country:
        stmt = stmt.where(CrimeIncident.country == country)
    if incident_category:
        stmt = stmt.where(CrimeIncident.incident_category == incident_category)
    if verification_status:
        stmt = stmt.where(CrimeIncident.verification_status == verification_status)
    if source_name:
        stmt = stmt.where(CrimeIncident.source_name == source_name)
    if bbox_parsed:
        west, south, east, north = bbox_parsed
        stmt = stmt.where(
            CrimeIncident.longitude_public >= west,
            CrimeIncident.longitude_public <= east,
            CrimeIncident.latitude_public >= south,
            CrimeIncident.latitude_public <= north,
        )
    stmt = (
        stmt.order_by(
            CrimeIncident.reported_at.desc().nullslast(), CrimeIncident.id.desc()
        )
        .offset(offset)
        .limit(limit + 1)
    )
    rows = db.scalars(stmt).all()
    truncated = len(rows) > limit
    aggregates = [
        r
        for r in rows[:limit]
        if is_public_crime_incident_mappable(r)
        and can_show_public_entity(db, "crime_incident", r).allowed
    ]
    filters_applied: dict = {
        "is_public": True,
        "review_status": list(PUBLIC_REVIEW_STATUSES),
        "aggregate_only": True,
    }
    if city:
        filters_applied["city"] = city
    if incident_category:
        filters_applied["incident_category"] = incident_category
    if bbox_parsed:
        filters_applied["bbox"] = bbox
    return {
        "type": "FeatureCollection",
        "returned_count": len(aggregates),
        "truncated": truncated,
        "filters_applied": filters_applied,
        "disclaimer": PLATFORM_DISCLAIMER,
        "features": [crime_incident_to_geojson_feature(agg) for agg in aggregates],
    }


_ARC_COORD_TYPES = ("court", "judge")


@router.get(
    "/api/map/relationship-arcs",
    dependencies=[Depends(rate_limit_map)],
)
def map_relationship_arcs(
    predicate: str | None = None,
    limit: int = Query(200, ge=1, le=250),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Return GeoJSON FeatureCollection of entity relationship arcs.

    Each feature is a LineString connecting two entities (courts or judges)
    via an active EntityGraphEdge. Returns an empty FeatureCollection with
    ``arcs_enabled: false`` if the feature flag is off or no edges pass the
    publication policy gates. Edges where either endpoint lacks a resolvable
    geographic coordinate are omitted silently.

    Publication policy (see ``app.policies.relationship_arc_policy``):
      * ``enable_public_relationship_arcs`` must be True
      * Each edge must carry >= ``public_relationship_arc_min_evidence`` evidence refs
      * Edge predicate must not match any causal/blame/guilt label pattern
      * Results hard-capped at ``public_relationship_arc_max_results``
    """
    # Clamp the DB query to the configured hard cap regardless of the query param
    effective_limit = min(limit, settings.public_relationship_arc_max_results)

    stmt = (
        select(EntityGraphEdge)
        .where(
            EntityGraphEdge.status == "active",
            EntityGraphEdge.subject_type.in_(_ARC_COORD_TYPES),
            EntityGraphEdge.object_type.in_(_ARC_COORD_TYPES),
        )
        .order_by(EntityGraphEdge.id.desc())
        .limit(effective_limit)
    )
    if predicate:
        stmt = stmt.where(EntityGraphEdge.predicate == predicate)
    edges = db.scalars(stmt).all()

    # Apply publication policy gates
    policy = evaluate_arc_request(list(edges), settings)
    if not policy.arcs_enabled:
        return {
            "type": "FeatureCollection",
            "features": [],
            "returned_count": 0,
            "arcs_enabled": False,
            "disclaimer": PLATFORM_DISCLAIMER,
        }

    # Collect IDs for batch-loading (only from policy-approved edges)
    court_ids: set[int] = set()
    judge_ids: set[int] = set()
    for e in policy.filtered_edges:
        (court_ids if e.subject_type == "court" else judge_ids).add(e.subject_id)
        (court_ids if e.object_type == "court" else judge_ids).add(e.object_id)

    courts: dict[int, Court] = {}
    if court_ids:
        courts = {
            c.id: c
            for c in db.scalars(
                select(Court)
                .options(selectinload(Court.location))
                .where(Court.id.in_(court_ids))
            ).all()
        }

    judges: dict[int, Judge] = {}
    if judge_ids:
        judges = {
            j.id: j
            for j in db.scalars(
                select(Judge)
                .options(selectinload(Judge.court).selectinload(Court.location))
                .where(Judge.id.in_(judge_ids))
            ).all()
        }

    def _resolve_coords(entity_type: str, entity_id: int) -> tuple[float, float] | None:
        if entity_type == "court":
            c = courts.get(entity_id)
            if c and c.location:
                return (c.location.longitude, c.location.latitude)
        elif entity_type == "judge":
            j = judges.get(entity_id)
            if j and j.court and j.court.location:
                return (j.court.location.longitude, j.court.location.latitude)
        return None

    features = []
    for e in policy.filtered_edges:
        src = _resolve_coords(e.subject_type, e.subject_id)
        dst = _resolve_coords(e.object_type, e.object_id)
        if src is None or dst is None or src == dst:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [list(src), list(dst)],
                },
                "properties": {
                    "edge_id": e.id,
                    "predicate": e.predicate,
                    "subject_type": e.subject_type,
                    "subject_id": e.subject_id,
                    "object_type": e.object_type,
                    "object_id": e.object_id,
                    "valid_from": e.valid_from.isoformat() if e.valid_from else None,
                    "valid_until": e.valid_until.isoformat() if e.valid_until else None,
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
        "returned_count": len(features),
        "arcs_enabled": True,
        "disclaimer": PLATFORM_DISCLAIMER,
    }
