from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AppleHealthSnapshot


def _to_local(dt: datetime) -> str:
    """Convert a datetime to the configured display timezone."""
    tz = ZoneInfo(get_settings().display_timezone)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz).isoformat()


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
            "captured_at": _to_local(r.captured_at),
            "period_start": _to_local(r.period_start),
            "period_end": _to_local(r.period_end),
        }
        for r in rows
    ]
