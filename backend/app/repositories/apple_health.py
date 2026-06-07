from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AppleHealthSnapshot


def get_latest_snapshot(db: Session, profile_id: int) -> AppleHealthSnapshot | None:
    """Return the most recent Apple Health snapshot for a profile."""
    return (
        db.query(AppleHealthSnapshot)
        .filter_by(profile_id=profile_id)
        .order_by(AppleHealthSnapshot.captured_at.desc())
        .first()
    )


def list_snapshot_metadata(
    db: Session, profile_id: int, limit: int = 30
) -> list[dict]:
    """Return lightweight snapshot metadata (id + timestamps, no payload) for a profile."""
    rows = (
        db.query(
            AppleHealthSnapshot.id,
            AppleHealthSnapshot.captured_at,
            AppleHealthSnapshot.period_start,
            AppleHealthSnapshot.period_end,
        )
        .filter(AppleHealthSnapshot.profile_id == profile_id)
        .order_by(AppleHealthSnapshot.captured_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "captured_at": r.captured_at.isoformat(),
            "period_start": r.period_start.isoformat(),
            "period_end": r.period_end.isoformat(),
        }
        for r in rows
    ]
