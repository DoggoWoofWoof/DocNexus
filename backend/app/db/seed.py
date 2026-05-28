import json
from pathlib import Path

from sqlmodel import Session

from backend.app.db.models import Physician


SEED_PATH = Path(__file__).resolve().parents[1] / "data" / "physicians_seed.json"


def seed_physicians(session: Session) -> int:
    rows = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    for row in rows:
        session.merge(Physician.from_seed_row(row))
    session.commit()
    return len(rows)
