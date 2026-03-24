from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import ProfileHealthAnalysis


def get_profile_health_analysis(db: Session, profile_id: int) -> ProfileHealthAnalysis | None:
    return db.get(ProfileHealthAnalysis, profile_id)


def save_profile_health_analysis(
    db: Session,
    *,
    profile_id: int,
    latest_measurement_id: int | None,
    measurement_ids: list[int],
    measurement_count: int,
    prompt_hash: str | None,
    settings_updated_at: datetime | None,
    summary: str | None,
    concern_level: str | None,
    highlights: list[str],
    generated_at: datetime | None,
    is_stale: bool,
    error_message: str | None,
) -> ProfileHealthAnalysis:
    analysis = get_profile_health_analysis(db, profile_id)
    if analysis is None:
        analysis = ProfileHealthAnalysis(profile_id=profile_id)
        db.add(analysis)
    analysis.latest_measurement_id = latest_measurement_id
    analysis.measurement_ids_json = measurement_ids
    analysis.measurement_count = measurement_count
    analysis.prompt_hash = prompt_hash
    analysis.settings_updated_at = settings_updated_at
    analysis.summary = summary
    analysis.concern_level = concern_level
    analysis.highlights_json = highlights
    analysis.generated_at = generated_at
    analysis.is_stale = is_stale
    analysis.error_message = error_message
    db.commit()
    db.refresh(analysis)
    return analysis
