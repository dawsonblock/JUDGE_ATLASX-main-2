import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Case, CaseParty, Court, Defendant, Judge, LegalSource
from app.services.anonymization import get_or_create_case_defendant
from app.services.text import normalize_docket, normalize_name


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def link_court(db: Session, courtlistener_id: str) -> Court | None:
    return db.scalar(select(Court).where(Court.courtlistener_id == courtlistener_id))


def link_judge(db: Session, name: str | None) -> Judge | None:
    if not name:
        return None
    return db.scalar(select(Judge).where(Judge.normalized_name == normalize_name(name)))


def link_case(db: Session, court: Court, docket_number: str) -> Case | None:
    return db.scalar(
        select(Case).where(
            Case.court_id == court.id,
            Case.normalized_docket_number == normalize_docket(docket_number),
        )
    )


def link_defendant_by_case(db: Session, case: Case, public_name: str | None) -> Defendant:
    normalized = normalize_name(public_name)
    existing_party = db.scalar(
        select(CaseParty).where(
            CaseParty.case_id == case.id,
            CaseParty.party_type == "defendant",
            CaseParty.normalized_name == normalized,
        )
    )
    if existing_party and existing_party.defendant:
        return existing_party.defendant

    defendant = get_or_create_case_defendant(db, public_name)
    db.add(
        CaseParty(
            case_id=case.id,
            defendant_id=defendant.id,
            party_type="defendant",
            public_name=public_name,
            normalized_name=normalized,
        )
    )
    db.flush()
    return defendant


def link_source_by_url(db: Session, url: str) -> LegalSource | None:
    return db.scalar(select(LegalSource).where(LegalSource.url_hash == url_hash(url)))

