from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import Select, and_, desc, func, select
from sqlalchemy.orm import Session

from app.models import Measurement


def list_measurements(
    db: Session,
    *,
    profile_id: int | None = None,
    limit: int = 100,
) -> list[Measurement]:
    query: Select[tuple[Measurement]] = select(Measurement)
    if profile_id is not None:
        query = query.where(Measurement.profile_id == profile_id)
    query = query.order_by(desc(Measurement.measured_at)).limit(limit)
    return list(db.scalars(query).all())


def recent_measurements(db: Session, profile_id: int, limit: int = 14) -> list[Measurement]:
    return list_measurements(db, profile_id=profile_id, limit=limit)


def add_measurement(db: Session, payload: dict) -> Measurement:
    measurement = Measurement(**payload)
    db.add(measurement)
    db.commit()
    db.refresh(measurement)
    return measurement


def reassign_measurement(db: Session, measurement_id: int, profile_id: int) -> Measurement | None:
    measurement = db.get(Measurement, measurement_id)
    if measurement is None:
        return None
    measurement.profile_id = profile_id
    measurement.assignment_state = "confirmed"
    measurement.note = "Manually reassigned"
    db.commit()
    db.refresh(measurement)
    return measurement


def delete_measurement(db: Session, measurement_id: int) -> bool:
    measurement = db.get(Measurement, measurement_id)
    if measurement is None:
        return False
    db.delete(measurement)
    db.commit()
    return True


def chart_series(db: Session, profile_id: int) -> dict[str, list[Measurement]]:
    rows = list(
        db.scalars(
            select(Measurement)
            .where(Measurement.profile_id == profile_id)
            .order_by(Measurement.measured_at.asc())
        ).all()
    )
    return {"rows": rows}


def is_duplicate(
    db: Session,
    *,
    profile_id: int,
    measured_at: datetime,
    weight_kg: float,
) -> bool:
    window_start = measured_at - timedelta(minutes=2)
    window_end = measured_at + timedelta(minutes=2)
    query = (
        select(func.count(Measurement.id))
        .where(Measurement.profile_id == profile_id)
        .where(and_(Measurement.measured_at >= window_start, Measurement.measured_at <= window_end))
        .where(and_(Measurement.weight_kg >= weight_kg - 0.05, Measurement.weight_kg <= weight_kg + 0.05))
    )
    return bool(db.scalar(query))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
