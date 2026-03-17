from __future__ import annotations

from datetime import date, datetime, timezone

from app.models import Profile
from app.services.metrics import normalize_measurement


def test_normalize_measurement_derives_secondary_metrics():
    profile = Profile(
        id=1,
        name="Alex",
        sex="male",
        birth_date=date(1989, 8, 17),
        height_cm=181,
        units="metric",
        color="#0f766e",
        active=True,
    )
    normalized = normalize_measurement(
        profile,
        {
            "measured_at": datetime(2026, 3, 16, 7, 10, tzinfo=timezone.utc),
            "weight_kg": 81.2,
            "fat_pct": 19.2,
            "water_pct": 55.6,
            "muscle_pct": 47.9,
            "skeletal_muscle_pct": 41.5,
            "visceral_fat": 9.8,
            "source": "replay",
        },
    )
    assert normalized["bmi"] == 24.8
    assert normalized["fat_weight_kg"] == 15.59
    assert normalized["water_weight_kg"] == 45.15
    assert normalized["status_by_metric"]["bmi"] == "healthy"
