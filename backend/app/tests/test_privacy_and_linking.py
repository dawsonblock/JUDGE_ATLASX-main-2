from app.db.session import SessionLocal
from app.models.entities import Case
from app.services.linker import link_defendant_by_case


def test_defendant_anonymization_label_sequence():
    with SessionLocal() as db:
        defendant = link_defendant_by_case(db, db.get(Case, 5), "Sample New Person")
        assert defendant.anonymized_id.startswith("DEF-")
        assert defendant.public_name == "Sample New Person"


def test_no_cross_case_defendant_merge_by_name_alone():
    with SessionLocal() as db:
        case_one = db.get(Case, 1)
        case_two = db.get(Case, 2)
        first = link_defendant_by_case(db, case_one, "Same Sample Name")
        second = link_defendant_by_case(db, case_two, "Same Sample Name")
        assert first.id != second.id

