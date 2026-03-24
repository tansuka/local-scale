from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.models import Profile
from app.services.anthropometric import measurement_date_from_raw

CALIBRATION_ENV_VAR = "LOCAL_SCALE_BIA_CALIBRATION_PATH"
DEFAULT_FEATURES = (
    "bias",
    "sex_male",
    "age_years",
    "height_cm",
    "weight_kg",
    "impedance_ohm",
    "bmi",
    "height_sq_over_impedance",
    "weight_times_height_sq_over_impedance",
)
TARGET_METRICS = (
    "fat_pct",
    "water_pct",
    "muscle_pct",
    "skeletal_muscle_pct",
    "visceral_fat",
)
METRIC_RANGES: dict[str, tuple[float, float]] = {
    "fat_pct": (3.0, 70.0),
    "water_pct": (20.0, 80.0),
    "muscle_pct": (10.0, 70.0),
    "skeletal_muscle_pct": (5.0, 60.0),
    "visceral_fat": (1.0, 30.0),
}


@dataclass(frozen=True, slots=True)
class CalibrationMetric:
    features: tuple[str, ...]
    coefficients: tuple[float, ...]


def age_on(birth_date: date, today: date) -> int:
    years = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years


def feature_map(
    *,
    profile: Profile,
    weight_kg: float,
    impedance_ohm: float,
    measurement_date: date,
) -> dict[str, float]:
    height_cm = float(profile.height_cm)
    height_m = height_cm / 100.0
    bmi = weight_kg / (height_m**2)
    height_sq_over_impedance = (height_cm**2) / max(impedance_ohm, 1.0)
    return {
        "bias": 1.0,
        "sex_male": 1.0 if profile.sex.lower().startswith("m") else 0.0,
        "age_years": float(age_on(profile.birth_date, measurement_date)),
        "height_cm": height_cm,
        "weight_kg": float(weight_kg),
        "impedance_ohm": float(impedance_ohm),
        "bmi": bmi,
        "height_sq_over_impedance": height_sq_over_impedance,
        "weight_times_height_sq_over_impedance": weight_kg * height_sq_over_impedance,
    }


def _clamp(metric: str, value: float) -> float:
    lower, upper = METRIC_RANGES[metric]
    return min(max(value, lower), upper)


def _calibration_path() -> Path | None:
    raw = os.getenv(CALIBRATION_ENV_VAR, "").strip()
    if not raw:
        return None
    return Path(raw)


@lru_cache(maxsize=1)
def _load_calibration_cached(path_value: str, mtime_ns: int) -> dict[str, CalibrationMetric]:
    del mtime_ns
    path = Path(path_value)
    payload = json.loads(path.read_text())
    metrics_payload = payload.get("metrics", {})
    calibration: dict[str, CalibrationMetric] = {}
    for metric, spec in metrics_payload.items():
        features = tuple(str(item) for item in spec.get("features", []))
        coefficients = tuple(float(item) for item in spec.get("coefficients", []))
        if not features or len(features) != len(coefficients):
            continue
        calibration[metric] = CalibrationMetric(features=features, coefficients=coefficients)
    return calibration


def load_calibration() -> dict[str, CalibrationMetric]:
    path = _calibration_path()
    if path is None or not path.exists():
        return {}
    stat = path.stat()
    return _load_calibration_cached(str(path), int(stat.st_mtime_ns))


def clear_calibration_cache() -> None:
    _load_calibration_cached.cache_clear()


def estimate_metrics(
    *,
    profile: Profile,
    weight_kg: float,
    impedance_ohm: float,
    measurement_date: date,
    calibration: dict[str, CalibrationMetric] | None = None,
) -> dict[str, float]:
    calibration = load_calibration() if calibration is None else calibration
    if not calibration:
        return {}

    features = feature_map(
        profile=profile,
        weight_kg=weight_kg,
        impedance_ohm=impedance_ohm,
        measurement_date=measurement_date,
    )
    estimates: dict[str, float] = {}
    for metric in TARGET_METRICS:
        spec = calibration.get(metric)
        if spec is None:
            continue
        value = 0.0
        for name, coefficient in zip(spec.features, spec.coefficients, strict=False):
            value += features.get(name, 0.0) * coefficient
        estimates[metric] = round(_clamp(metric, value), 2)
    return estimates


def estimate_from_raw(profile: Profile, raw: dict[str, Any]) -> tuple[dict[str, float], dict[str, str]]:
    impedance = raw.get("impedance_ohm")
    if impedance is None:
        impedance = (raw.get("raw_payload_json") or {}).get("impedance_ohm")
    if impedance is None or raw.get("weight_kg") is None:
        return {}, {}

    calibration = load_calibration()
    if not calibration:
        return {}, {}

    measurement_date = measurement_date_from_raw(raw)
    estimates = estimate_metrics(
        profile=profile,
        weight_kg=float(raw["weight_kg"]),
        impedance_ohm=float(impedance),
        measurement_date=measurement_date,
        calibration=calibration,
    )
    source_metric_map = {
        metric: "bia_calibrated"
        for metric in estimates
    }
    return estimates, source_metric_map


def solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float]:
    size = len(vector)
    augmented = [row[:] + [value] for row, value in zip(matrix, vector, strict=True)]
    for pivot in range(size):
        pivot_row = max(range(pivot, size), key=lambda row: abs(augmented[row][pivot]))
        if abs(augmented[pivot_row][pivot]) < 1e-12:
            raise ValueError("Calibration matrix is singular; add more varied samples.")
        augmented[pivot], augmented[pivot_row] = augmented[pivot_row], augmented[pivot]
        pivot_value = augmented[pivot][pivot]
        for column in range(pivot, size + 1):
            augmented[pivot][column] /= pivot_value
        for row in range(size):
            if row == pivot:
                continue
            factor = augmented[row][pivot]
            for column in range(pivot, size + 1):
                augmented[row][column] -= factor * augmented[pivot][column]
    return [augmented[index][size] for index in range(size)]


def fit_metric(
    samples: list[dict[str, float]],
    *,
    metric: str,
    features: tuple[str, ...] = DEFAULT_FEATURES,
    ridge_lambda: float = 1e-6,
) -> CalibrationMetric:
    if not samples:
        raise ValueError("No samples available for calibration.")

    rows = [
        [float(sample.get(feature, 0.0)) for feature in features]
        for sample in samples
    ]
    targets = [float(sample[metric]) for sample in samples]
    size = len(features)
    xtx = [[0.0 for _ in range(size)] for _ in range(size)]
    xty = [0.0 for _ in range(size)]
    for row, target in zip(rows, targets, strict=True):
        for i in range(size):
            xty[i] += row[i] * target
            for j in range(size):
                xtx[i][j] += row[i] * row[j]
    for index in range(size):
        xtx[index][index] += ridge_lambda
    coefficients = solve_linear_system(xtx, xty)
    return CalibrationMetric(features=features, coefficients=tuple(coefficients))
