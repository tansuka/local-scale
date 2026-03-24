from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Measurement
from app.models import Profile

ANTHROPOMETRIC_SOURCE = "anthropometric_estimated"
VAI_SOURCE = "vai_estimated"
METRIC_RANGES: dict[str, tuple[float, float]] = {
    "fat_pct": (3.0, 70.0),
    "water_pct": (20.0, 80.0),
}


def age_on(birth_date: date, today: date) -> int:
    years = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years


def measurement_date_from_raw(raw: dict[str, Any]) -> date:
    candidate = raw.get("measurement_date")
    if isinstance(candidate, datetime):
        return candidate.date()
    if isinstance(candidate, date):
        return candidate

    measured_at = raw.get("measured_at")
    if isinstance(measured_at, datetime):
        return measured_at.date()
    return date.today()


def _clamp(metric: str, value: float) -> float:
    lower, upper = METRIC_RANGES[metric]
    return min(max(value, lower), upper)


def estimate_fat_pct(
    *,
    profile: Profile,
    weight_kg: float,
    measurement_date: date,
) -> float:
    height_m = float(profile.height_cm) / 100.0
    bmi = weight_kg / (height_m**2)
    age_years = age_on(profile.birth_date, measurement_date)
    is_male = 1.0 if profile.sex.lower().startswith("m") else 0.0
    if age_years >= 16:
        value = (1.2 * bmi) + (0.23 * age_years) - (10.8 * is_male) - 5.4
    else:
        value = (1.294 * bmi) + (0.20 * age_years) - (11.4 * is_male) - 8.0
    return round(_clamp("fat_pct", value), 2)


def estimate_total_body_water_kg(*, profile: Profile, weight_kg: float) -> float:
    height_cm = float(profile.height_cm)
    if profile.sex.lower().startswith("m"):
        return (0.194786 * height_cm) + (0.296785 * weight_kg) - 14.012934
    return (0.34454 * height_cm) + (0.183809 * weight_kg) - 35.270121


def estimate_skeletal_muscle_mass_kg(
    *,
    profile: Profile,
    weight_kg: float,
    measurement_date: date,
) -> float:
    height_m = float(profile.height_cm) / 100.0
    age_years = age_on(profile.birth_date, measurement_date)
    sex_term = 1.0 if profile.sex.lower().startswith("m") else 0.0
    race_term = 0.0
    value = (
        (0.244 * weight_kg)
        + (7.80 * height_m)
        - (0.098 * age_years)
        + (6.6 * sex_term)
        + race_term
        - 3.3
    )
    return round(max(value, 5.0), 2)


def estimate_water_pct(*, profile: Profile, weight_kg: float) -> float:
    total_body_water_kg = estimate_total_body_water_kg(
        profile=profile,
        weight_kg=weight_kg,
    )
    water_pct = (total_body_water_kg / weight_kg) * 100.0
    return round(_clamp("water_pct", water_pct), 2)


def estimate_visceral_adiposity_index(
    *,
    profile: Profile,
    weight_kg: float,
    waist_cm: float | None,
    triglycerides_mmol_l: float | None,
    hdl_mmol_l: float | None,
    measurement_date: date,
) -> float | None:
    if waist_cm is None or triglycerides_mmol_l is None or hdl_mmol_l is None:
        return None
    age_years = age_on(profile.birth_date, measurement_date)
    if age_years < 16:
        return None
    height_m = float(profile.height_cm) / 100.0
    bmi = weight_kg / (height_m**2)
    if bmi <= 0 or bmi >= 40 or triglycerides_mmol_l <= 0 or hdl_mmol_l <= 0:
        return None
    if triglycerides_mmol_l > 3.15:
        return None

    if profile.sex.lower().startswith("m"):
        value = (
            (waist_cm / (39.68 + (1.88 * bmi)))
            * (triglycerides_mmol_l / 1.03)
            * (1.31 / hdl_mmol_l)
        )
    else:
        value = (
            (waist_cm / (36.58 + (1.89 * bmi)))
            * (triglycerides_mmol_l / 0.81)
            * (1.52 / hdl_mmol_l)
        )
    return round(max(value, 0.1), 2)


def estimate_metrics(
    *,
    profile: Profile,
    weight_kg: float,
    waist_cm: float | None = None,
    triglycerides_mmol_l: float | None = None,
    hdl_mmol_l: float | None = None,
    measurement_date: date,
) -> dict[str, float]:
    estimates = {
        "fat_pct": estimate_fat_pct(
            profile=profile,
            weight_kg=weight_kg,
            measurement_date=measurement_date,
        ),
        "skeletal_muscle_weight_kg": estimate_skeletal_muscle_mass_kg(
            profile=profile,
            weight_kg=weight_kg,
            measurement_date=measurement_date,
        ),
        "water_pct": estimate_water_pct(
            profile=profile,
            weight_kg=weight_kg,
        ),
    }
    visceral_adiposity_index = estimate_visceral_adiposity_index(
        profile=profile,
        weight_kg=weight_kg,
        waist_cm=waist_cm,
        triglycerides_mmol_l=triglycerides_mmol_l,
        hdl_mmol_l=hdl_mmol_l,
        measurement_date=measurement_date,
    )
    if visceral_adiposity_index is not None:
        estimates["visceral_adiposity_index"] = visceral_adiposity_index
    return estimates


def backfill_missing_measurements(db: Session) -> int:
    rows = list(
        db.execute(
            select(Measurement, Profile)
            .join(Profile, Measurement.profile_id == Profile.id)
            .order_by(Profile.id.asc(), Measurement.measured_at.asc(), Measurement.id.asc())
        ).all()
    )
    if not rows:
        return 0

    from app.services.metrics import normalize_measurement

    updated = 0
    last_known_waist_by_profile: dict[int, float] = {}
    for measurement, profile in rows:
        waist_cm = measurement.waist_cm
        source_metric_map = dict(measurement.source_metric_map or {})
        if waist_cm is None:
            waist_cm = last_known_waist_by_profile.get(profile.id)
            if waist_cm is not None and "waist_cm" not in source_metric_map:
                source_metric_map["waist_cm"] = "carried_forward"

        normalized = normalize_measurement(
            profile,
            {
                "measured_at": measurement.measured_at,
                "measurement_date": measurement.measured_at.date(),
                "source": measurement.source,
                "weight_kg": measurement.weight_kg,
                "waist_cm": waist_cm,
                "triglycerides_mmol_l": measurement.triglycerides_mmol_l,
                "hdl_mmol_l": measurement.hdl_mmol_l,
                "bmi": measurement.bmi,
                "fat_pct": measurement.fat_pct,
                "fat_weight_kg": measurement.fat_weight_kg,
                "skeletal_muscle_pct": measurement.skeletal_muscle_pct,
                "skeletal_muscle_weight_kg": measurement.skeletal_muscle_weight_kg,
                "muscle_pct": measurement.muscle_pct,
                "muscle_weight_kg": measurement.muscle_weight_kg,
                "visceral_fat": measurement.visceral_fat,
                "visceral_adiposity_index": measurement.visceral_adiposity_index,
                "water_pct": measurement.water_pct,
                "water_weight_kg": measurement.water_weight_kg,
                "bone_weight_kg": measurement.bone_weight_kg,
                "bmr_kcal": measurement.bmr_kcal,
                "metabolic_age": measurement.metabolic_age,
                "body_age": measurement.body_age,
                "source_metric_map": source_metric_map,
                "raw_payload_json": dict(measurement.raw_payload_json or {}),
            },
        )

        changed = False
        for field, value in normalized.items():
            if field == "measured_at":
                continue
            if getattr(measurement, field) != value:
                setattr(measurement, field, value)
                changed = True
        if measurement.waist_cm is not None:
            last_known_waist_by_profile[profile.id] = float(measurement.waist_cm)
        if changed:
            updated += 1

    if updated:
        db.commit()
    return updated
