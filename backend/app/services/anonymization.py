from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import Defendant
from app.services.text import normalize_name


def next_defendant_label(db: Session) -> str:
    count = db.scalar(select(func.count(Defendant.id))) or 0
    return f"DEF-{count + 1:06d}"


def get_or_create_case_defendant(db: Session, public_name: str | None) -> Defendant:
    defendant = Defendant(
        anonymized_id=next_defendant_label(db),
        public_name=public_name,
        normalized_public_name=normalize_name(public_name),
    )
    db.add(defendant)
    db.flush()
    return defendant

