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
    assert normalized["skeletal_muscle_weight_kg"] == 33.7
    assert normalized["status_by_metric"]["bmi"] == "healthy"
    # Only skeletal_muscle_pct was supplied, so the mass is derived from it
    # (81.2 kg x 41.5%) rather than estimated, and is classified: SMI 10.29 kg/m²
    # is at or below Janssen's 10.75 cutpoint for men.
    assert normalized["source_metric_map"]["skeletal_muscle_weight_kg"] == "computed"
    assert normalized["status_by_metric"]["skeletal_muscle_weight_kg"] == "low"


def test_reported_skeletal_muscle_pct_is_not_replaced_by_an_estimated_mass():
    profile = Profile(
        id=1,
        name="Alex",
        sex="male",
        birth_date=date(1985, 1, 1),
        height_cm=180,
        units="metric",
        color="#0f766e",
        active=True,
    )
    normalized = normalize_measurement(
        profile,
        {
            "measured_at": datetime(2026, 10, 1, 7, 0, tzinfo=timezone.utc),
            "source": "import",
            "weight_kg": 90.0,
            "skeletal_muscle_pct": 45.0,
            "source_metric_map": {"skeletal_muscle_pct": "import"},
        },
    )

    assert normalized["skeletal_muscle_pct"] == 45.0
    assert normalized["skeletal_muscle_weight_kg"] == 40.5
    assert normalized["source_metric_map"]["skeletal_muscle_weight_kg"] == "computed"
    # SMI 40.5 / 1.8² = 12.5 kg/m², above the 10.75 cutpoint.
    assert normalized["status_by_metric"]["skeletal_muscle_weight_kg"] == "healthy"
