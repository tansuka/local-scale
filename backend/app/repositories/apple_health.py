from __future__ import annotations

from datetime import date, datetime, timezone
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


def get_snapshot_by_date(
    db: Session, profile_id: int, snapshot_date: date
) -> AppleHealthSnapshot | None:
    """Return the snapshot for one specific local date, or None if that day was never synced.

    Sync upserts one row per (profile_id, snapshot_date), so at most one row matches;
    the ordering only guards against legacy rows that predate the upsert migration.
    """
    return (
        db.query(AppleHealthSnapshot)
        .filter_by(profile_id=profile_id, snapshot_date=snapshot_date)
        .order_by(AppleHealthSnapshot.captured_at.desc())
        .first()
    )


def list_snapshot_dates(db: Session, profile_id: int, limit: int = 10) -> list[str]:
    """Return the most recent snapshot dates (newest first) as ISO strings."""
    rows = (
        db.query(AppleHealthSnapshot.snapshot_date)
        .filter(
            AppleHealthSnapshot.profile_id == profile_id,
            AppleHealthSnapshot.snapshot_date.isnot(None),
        )
        .order_by(AppleHealthSnapshot.snapshot_date.desc())
        .limit(limit)
        .all()
    )
    return [r.snapshot_date.isoformat() for r in rows]


def list_snapshot_metadata(
    db: Session, profile_id: int, limit: int = 30
) -> list[dict]:
    """Return lightweight snapshot metadata (id + timestamps, no payload) for a profile."""
    rows = (
        db.query(
            AppleHealthSnapshot.id,
            AppleHealthSnapshot.snapshot_date,
            AppleHealthSnapshot.captured_at,
            AppleHealthSnapshot.updated_at,
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
            "snapshot_date": r.snapshot_date.isoformat() if r.snapshot_date else None,
            "captured_at": _to_local(r.captured_at),
            "updated_at": _to_local(r.updated_at) if r.updated_at else None,
            "period_start": _to_local(r.period_start),
            "period_end": _to_local(r.period_end),
        }
        for r in rows
    ]
