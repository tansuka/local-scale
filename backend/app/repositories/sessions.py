from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import WeighSession


def create_session(db: Session, payload: dict) -> WeighSession:
    session = WeighSession(**payload)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_session(db: Session, session_id: str) -> WeighSession | None:
    return db.get(WeighSession, session_id)


def latest_session(db: Session) -> WeighSession | None:
    return db.scalar(select(WeighSession).order_by(desc(WeighSession.started_at)))
