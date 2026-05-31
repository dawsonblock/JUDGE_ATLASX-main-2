from datetime import date, datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.admin import log_mutation, require_public_event_actor
from app.auth.actor import AdminActor
from app.db.session import get_db
from app.models.entities import (
    Case,
    Defendant,
    Event,
    EventDefendant,
    Judge,
    LegalSource,
    Location,
    Court,
)
from app.schemas.api import (
    CaseOut,
    EventCreate,
    EventOut,
    JudgeSummaryOut,
    SourceOut,
)
from app.serializers.public import (
    case_options,
    case_to_public_dict,
    event_options,
    filtered_events_query,
    serialize_event,
    source_panel_payload,
    source_to_public_dict,
    entity_by_type,
)
from app.services.constants import ALLOWED_EVENT_TYPES, PUBLIC_REVIEW_STATUSES
from app.policies.publication_policy import can_show_public_entity

router = APIRouter()


def _policy_visible(db: Session, entity_type: str, entity) -> bool:
    return can_show_public_entity(db, entity_type, entity).allowed


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@router.get("/api/events", response_model=list[EventOut])
def list_events(
    start: date | None = None,
    end: date | None = None,
    court_id: int | None = None,
    judge_id: int | None = None,
    event_type: str | None = None,
    repeat_offender_indicator: bool | None = None,
    repeat_offender: bool | None = None,
    verified_only: bool = False,
    source_type: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    indicator_filter = (
        repeat_offender_indicator
        if repeat_offender_indicator is not None
        else repeat_offender
    )
    events = (
        db.scalars(
            filtered_events_query(
                start,
                end,
                court_id,
                judge_id,
                event_type,
                indicator_filter,
                verified_only,
                source_type,
                limit,
                offset,
            )
        )
        .unique()
        .all()
    )
    return [
        serialize_event(event)
        for event in events
        if _policy_visible(db, "event", event)
    ]


@router.get("/api/events/{event_id}", response_model=EventOut)
def get_event(event_id: str, db: Session = Depends(get_db)):
    event = db.scalar(
        select(Event).options(*event_options()).where(Event.event_id == event_id)
    )
    if not event or not _policy_visible(db, "event", event):
        raise HTTPException(status_code=404, detail="Event not found")
    return serialize_event(event)


@router.post(
    "/api/events",
    response_model=EventOut,
    status_code=201,
)
def create_event(
    payload: EventCreate,
    request: Request,
    actor: AdminActor = Depends(require_public_event_actor),
    db: Session = Depends(get_db),
):
    if payload.event_type not in ALLOWED_EVENT_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported event type")
    if not db.get(Court, payload.court_id):
        raise HTTPException(
            status_code=422, detail="court_id does not reference an existing court"
        )
    if not db.get(Case, payload.case_id):
        raise HTTPException(
            status_code=422, detail="case_id does not reference an existing case"
        )
    if not db.get(Location, payload.primary_location_id):
        raise HTTPException(
            status_code=422,
            detail="primary_location_id does not reference an existing location",
        )
    if payload.judge_id is not None and not db.get(Judge, payload.judge_id):
        raise HTTPException(
            status_code=422, detail="judge_id does not reference an existing judge"
        )
    data = payload.model_dump()
    repeat_offender_indicator = data.pop("repeat_offender_indicator")
    event = Event(
        event_id=f"EVT-{uuid4().hex[:12].upper()}",
        last_verified_at=datetime.now(timezone.utc) if payload.verified_flag else None,
        repeat_offender_indicator=repeat_offender_indicator,
        **data,
    )
    db.add(event)
    db.flush()
    try:
        log_mutation(
            action="event_create",
            entity_type="event",
            entity_id=event.event_id,
            payload={"event_type": event.event_type, "case_id": event.case_id},
            request=request,
            actor=actor,
            db=db,
            fail_closed=True,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Audit logging failed; mutation aborted",
        )
    db.refresh(event)
    event = db.scalar(
        select(Event).options(*event_options()).where(Event.id == event.id)
    )
    return serialize_event(event)


def _public_event_count(db: Session, judge_id: int) -> int:
    """Count public reviewed events linked to this judge."""
    return (
        db.scalar(
            select(func.count(Event.id)).where(
                Event.judge_id == judge_id,
                Event.public_visibility.is_(True),
                Event.review_status.in_(PUBLIC_REVIEW_STATUSES),
            )
        )
        or 0
    )


def _judge_summary(db: Session, judge: Judge) -> JudgeSummaryOut:
    return JudgeSummaryOut(
        id=judge.id,
        name=judge.name,
        court_id=judge.court_id,
        cl_person_id=judge.cl_person_id,
        public_event_count=_public_event_count(db, judge.id),
    )


@router.get("/api/judges", response_model=list[JudgeSummaryOut])
def list_judges(db: Session = Depends(get_db)):
    judges_with_events = db.scalars(
        select(Judge)
        .where(
            Judge.id.in_(
                select(Event.judge_id).where(
                    Event.public_visibility.is_(True),
                    Event.review_status.in_(PUBLIC_REVIEW_STATUSES),
                    Event.judge_id.is_not(None),
                )
            )
        )
        .order_by(Judge.name)
    ).all()
    return [_judge_summary(db, j) for j in judges_with_events]


@router.get("/api/judges/{judge_id}", response_model=JudgeSummaryOut)
def get_judge(judge_id: int, db: Session = Depends(get_db)):
    judge = db.get(Judge, judge_id)
    if not judge:
        raise HTTPException(status_code=404, detail="Judge not found")
    if _public_event_count(db, judge_id) == 0:
        raise HTTPException(status_code=404, detail="Judge not found")
    return _judge_summary(db, judge)


@router.get("/api/judges/{judge_id}/events", response_model=list[EventOut])
def judge_events(judge_id: int, db: Session = Depends(get_db)):
    events = (
        db.scalars(
            select(Event)
            .options(*event_options())
            .where(
                Event.judge_id == judge_id,
                Event.public_visibility.is_(True),
                Event.review_status.in_(PUBLIC_REVIEW_STATUSES),
            )
        )
        .unique()
        .all()
    )
    return [
        serialize_event(event)
        for event in events
        if _policy_visible(db, "event", event)
    ]


@router.get("/api/cases", response_model=list[CaseOut])
def list_cases(db: Session = Depends(get_db)):
    cases = db.scalars(
        select(Case)
        .where(
            Case.id.in_(
                select(Event.case_id).where(
                    Event.public_visibility.is_(True),
                    Event.review_status.in_(PUBLIC_REVIEW_STATUSES),
                    Event.case_id.is_not(None),
                )
            )
        )
        .order_by(Case.filed_date.desc().nullslast())
        .limit(200)
    ).all()
    return [case_to_public_dict(case) for case in cases]


@router.get("/api/cases/{case_id}", response_model=CaseOut)
def get_case(case_id: int, db: Session = Depends(get_db)):
    case = db.scalar(select(Case).options(*case_options()).where(Case.id == case_id))
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    event = db.scalar(
        select(Event)
        .options(*event_options())
        .where(
            Event.case_id == case_id,
            Event.public_visibility.is_(True),
            Event.review_status.in_(PUBLIC_REVIEW_STATUSES),
        )
        .limit(1)
    )
    if not event:
        raise HTTPException(status_code=404, detail="Case not found")
    return case_to_public_dict(case, event)


@router.get("/api/cases/{case_id}/timeline", response_model=list[EventOut])
def case_timeline(case_id: int, db: Session = Depends(get_db)):
    events = (
        db.scalars(
            select(Event)
            .options(*event_options())
            .where(
                Event.case_id == case_id,
                Event.public_visibility.is_(True),
                Event.review_status.in_(PUBLIC_REVIEW_STATUSES),
            )
            .order_by(Event.decision_date)
        )
        .unique()
        .all()
    )
    return [
        serialize_event(event)
        for event in events
        if _policy_visible(db, "event", event)
    ]


@router.get("/api/defendants/{defendant_id}")
def get_defendant(defendant_id: int, db: Session = Depends(get_db)):
    defendant = db.get(Defendant, defendant_id)
    if not defendant:
        raise HTTPException(status_code=404, detail="Defendant not found")
    has_public_event = db.scalar(
        select(Event.id)
        .join(EventDefendant, EventDefendant.event_id == Event.id)
        .where(
            EventDefendant.defendant_id == defendant_id,
            Event.public_visibility.is_(True),
            Event.review_status.in_(PUBLIC_REVIEW_STATUSES),
        )
        .limit(1)
    )
    if not has_public_event:
        raise HTTPException(status_code=404, detail="Defendant not found")
    return {
        "id": defendant.id,
        "anonymized_id": defendant.anonymized_id,
        "display_label": defendant.anonymized_id,
        "warning": (
            "No personal location tracking. Events are mapped to courts"
            " and verified legal records only."
        ),
    }


@router.get("/api/defendants/{defendant_id}/timeline", response_model=list[EventOut])
def defendant_timeline(defendant_id: int, db: Session = Depends(get_db)):
    events = (
        db.scalars(
            select(Event)
            .options(*event_options())
            .join(EventDefendant)
            .where(
                EventDefendant.defendant_id == defendant_id,
                Event.public_visibility.is_(True),
                Event.review_status.in_(PUBLIC_REVIEW_STATUSES),
            )
            .order_by(Event.decision_date)
        )
        .unique()
        .all()
    )
    return [
        serialize_event(event)
        for event in events
        if _policy_visible(db, "event", event)
    ]


@router.get("/api/sources/{source_id}", response_model=SourceOut)
def get_source(source_id: str, db: Session = Depends(get_db)):
    source = db.scalar(select(LegalSource).where(LegalSource.source_id == source_id))
    if not source and source_id.isdigit():
        source = db.get(LegalSource, int(source_id))
    if not source or not _policy_visible(db, "source", source):
        raise HTTPException(status_code=404, detail="Source not found")
    return source_to_public_dict(source)


@router.get("/api/sources", response_model=list[SourceOut])
def list_sources(db: Session = Depends(get_db)):
    sources = db.scalars(
        select(LegalSource)
        .where(
            LegalSource.public_visibility.is_(True),
            LegalSource.review_status.in_(PUBLIC_REVIEW_STATUSES),
        )
        .order_by(LegalSource.id)
    ).all()
    return [
        source_to_public_dict(source)
        for source in sources
        if _policy_visible(db, "source", source)
    ]


@router.get("/api/evidence/source-panel/{entity_type}/{entity_id}")
def source_panel(entity_type: str, entity_id: str, db: Session = Depends(get_db)):
    entity = entity_by_type(db, entity_type, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Evidence not found")
    if entity_type == "event" and not _policy_visible(db, "event", entity):
        raise HTTPException(status_code=404, detail="Evidence not found")
    if entity_type == "crime_incident" and not _policy_visible(db, "crime_incident", entity):
        raise HTTPException(status_code=404, detail="Evidence not found")
    if entity_type == "source" and not _policy_visible(db, "source", entity):
        raise HTTPException(status_code=404, detail="Evidence not found")
    return source_panel_payload(entity_type, entity)
