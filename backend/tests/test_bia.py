from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.models import Profile
from app.services.bia import clear_calibration_cache, estimate_from_raw, estimate_metrics, fit_metric


def test_fit_metric_recovers_simple_linear_relationship():
    samples = [
        {
            "bias": 1.0,
            "sex_male": 1.0,
            "age_years": 30.0,
            "height_cm": 180.0,
            "weight_kg": 74.0,
            "impedance_ohm": 500.0,
            "bmi": 22.8,
            "height_sq_over_impedance": 64.8,
            "weight_times_height_sq_over_impedance": 4795.2,
            "fat_pct": 20.0 + 0.2 * 74.0 - 0.01 * 500.0,
        },
        {
            "bias": 1.0,
            "sex_male": 1.0,
            "age_years": 30.0,
            "height_cm": 180.0,
            "weight_kg": 75.0,
            "impedance_ohm": 492.0,
            "bmi": 23.1,
            "height_sq_over_impedance": 65.8536585366,
            "weight_times_height_sq_over_impedance": 4939.024390245,
            "fat_pct": 20.0 + 0.2 * 75.0 - 0.01 * 492.0,
        },
        {
            "bias": 1.0,
            "sex_male": 1.0,
            "age_years": 30.0,
            "height_cm": 180.0,
            "weight_kg": 76.0,
            "impedance_ohm": 508.0,
            "bmi": 23.5,
            "height_sq_over_impedance": 63.7795275591,
            "weight_times_height_sq_over_impedance": 4847.2440944916,
            "fat_pct": 20.0 + 0.2 * 76.0 - 0.01 * 508.0,
        },
    ]

    fitted = fit_metric(samples, metric="fat_pct", features=("bias", "weight_kg", "impedance_ohm"))

    assert fitted.features == ("bias", "weight_kg", "impedance_ohm")
    predicted = (
        fitted.coefficients[0]
        + fitted.coefficients[1] * 75.0
        + fitted.coefficients[2] * 492.0
    )
    assert round(predicted, 3) == round(20.0 + 0.2 * 75.0 - 0.01 * 492.0, 3)


def test_estimate_from_raw_uses_calibration_file(monkeypatch, tmp_path: Path):
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

    profile = Profile(
        id=1,
        name="Alex",
        sex="male",
        birth_date=date(1990, 1, 1),
        height_cm=180,
        units="metric",
        color="#0f766e",
        active=True,
    )

    estimates, source_metric_map = estimate_from_raw(
        profile,
        {
            "weight_kg": 74.19,
            "measurement_date": date(2026, 3, 17),
            "raw_payload_json": {"impedance_ohm": 500},
        },
    )

    assert estimates["fat_pct"] == 22.42
    assert estimates["water_pct"] == 54.84
    assert source_metric_map == {
        "fat_pct": "bia_calibrated",
        "water_pct": "bia_calibrated",
    }

    clear_calibration_cache()


def test_estimate_metrics_clamps_ranges():
    profile = Profile(
        id=1,
        name="Alex",
        sex="male",
        birth_date=date(1990, 1, 1),
        height_cm=180,
        units="metric",
        color="#0f766e",
        active=True,
    )
    estimates = estimate_metrics(
        profile=profile,
        weight_kg=74.19,
        impedance_ohm=500,
        measurement_date=date(2026, 3, 17),
        calibration={
            "fat_pct": type("Spec", (), {"features": ("bias",), "coefficients": (120.0,)})(),
        },
    )
    assert estimates["fat_pct"] == 70.0
