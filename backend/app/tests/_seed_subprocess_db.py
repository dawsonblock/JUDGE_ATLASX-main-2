import os, sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parents[3]))
from app.db.session import Base, SessionLocal, engine
from app.models.entities import *  # noqa
from app.seed.source_registry import seed_source_registry
Base.metadata.create_all(bind=engine)
with SessionLocal() as db:
    seed_source_registry(db)
    db.commit()
print('seeded')
