from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from app.models import Profile
from app.services.bia import clear_calibration_cache
from app.services.metrics import normalize_measurement


def _profile(*, sex: str = "male") -> Profile:
    return Profile(
        id=1,
        name="Alex",
        sex=sex,
        birth_date=date(1990, 1, 1),
        height_cm=180,
        units="metric",
        color="#0f766e",
        active=True,
    )


def test_normalize_measurement_falls_back_to_anthropometric_estimates():
    normalized = normalize_measurement(
        _profile(),
        {
            "measured_at": datetime(2026, 3, 17, 7, 10, tzinfo=timezone.utc),
            "source": "live",
            "weight_kg": 74.19,
            "source_metric_map": {"weight_kg": "live"},
        },
    )

    assert normalized["fat_pct"] == 19.56
    assert normalized["water_pct"] == 58.05
    assert normalized["fat_weight_kg"] == 14.51
    assert normalized["skeletal_muscle_weight_kg"] == 31.91
    assert normalized["water_weight_kg"] == 43.07
    assert normalized["source_metric_map"]["fat_pct"] == "anthropometric_estimated"
    assert normalized["source_metric_map"]["water_pct"] == "anthropometric_estimated"
    assert (
        normalized["source_metric_map"]["skeletal_muscle_weight_kg"]
        == "anthropometric_estimated"
    )
    assert normalized["status_by_metric"]["skeletal_muscle_weight_kg"] == "healthy"


def test_normalize_measurement_preserves_explicit_values_over_anthropometric_fallback():
    normalized = normalize_measurement(
        _profile(),
        {
            "measured_at": datetime(2026, 3, 17, 7, 10, tzinfo=timezone.utc),
            "source": "import",
            "weight_kg": 74.19,
            "fat_pct": 18.3,
            "water_pct": 56.4,
            "source_metric_map": {
                "weight_kg": "import",
                "fat_pct": "import",
                "water_pct": "import",
            },
        },
    )

    assert normalized["fat_pct"] == 18.3
    assert normalized["water_pct"] == 56.4
    assert normalized["source_metric_map"]["fat_pct"] == "import"
    assert normalized["source_metric_map"]["water_pct"] == "import"
    assert normalized["source_metric_map"]["skeletal_muscle_weight_kg"] == "anthropometric_estimated"


def test_normalize_measurement_prefers_bia_calibration_over_anthropometric_fallback(
    monkeypatch,
    tmp_path: Path,
):
    calibration_path = tmp_path / "bia-calibration.json"
    calibration_path.write_text(
        json.dumps(
            {
                "version": 1,
                "metrics": {
                    "fat_pct": {
                        "features": ["bias", "weight_kg", "impedance_ohm"],
                        "coefficients": [10.0, 0.1, 0.01],
                    },
                    "water_pct": {
                        "features": ["bias", "weight_kg"],
                        "coefficients": [40.0, 0.2],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("LOCAL_SCALE_BIA_CALIBRATION_PATH", str(calibration_path))
    clear_calibration_cache()

    normalized = normalize_measurement(
        _profile(),
        {
            "measured_at": datetime(2026, 3, 17, 7, 10, tzinfo=timezone.utc),
            "source": "live",
            "weight_kg": 74.19,
            "raw_payload_json": {"impedance_ohm": 500},
            "source_metric_map": {"weight_kg": "live"},
        },
    )

    assert normalized["fat_pct"] == 22.42
    assert normalized["water_pct"] == 54.84
    assert normalized["source_metric_map"]["fat_pct"] == "bia_calibrated"
    assert normalized["source_metric_map"]["water_pct"] == "bia_calibrated"
    assert normalized["source_metric_map"]["skeletal_muscle_weight_kg"] == "anthropometric_estimated"

    clear_calibration_cache()
