from __future__ import annotations

from datetime import date

from app.models import Measurement, Profile
from app.services.classification import classify_metrics


def age_on(birth_date: date, today: date) -> int:
    years = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years


def _healthy_midpoint(sex: str) -> tuple[float, float]:
    if sex.lower().startswith("m"):
        return 14.0, 56.0
    return 27.0, 52.0


def normalize_measurement(profile: Profile, raw: dict) -> dict:
    weight_kg = float(raw["weight_kg"])
    height_m = profile.height_cm / 100.0
    bmi = raw.get("bmi") or round(weight_kg / (height_m**2), 1)

    fat_pct = raw.get("fat_pct")
    fat_weight_kg = raw.get("fat_weight_kg")
    if fat_pct is not None and fat_weight_kg is None:
        fat_weight_kg = round(weight_kg * fat_pct / 100.0, 2)

    water_pct = raw.get("water_pct")
    water_weight_kg = raw.get("water_weight_kg")
    if water_pct is not None and water_weight_kg is None:
        water_weight_kg = round(weight_kg * water_pct / 100.0, 2)

    muscle_pct = raw.get("muscle_pct")
    muscle_weight_kg = raw.get("muscle_weight_kg")
    if muscle_pct is not None and muscle_weight_kg is None:
        muscle_weight_kg = round(weight_kg * muscle_pct / 100.0, 2)

    skeletal_muscle_pct = raw.get("skeletal_muscle_pct")
    skeletal_muscle_weight_kg = raw.get("skeletal_muscle_weight_kg")
    if skeletal_muscle_pct is not None and skeletal_muscle_weight_kg is None:
        skeletal_muscle_weight_kg = round(weight_kg * skeletal_muscle_pct / 100.0, 2)

    bone_weight_kg = raw.get("bone_weight_kg")
    if bone_weight_kg is None:
        bone_weight_kg = round(weight_kg * 0.04, 2)

    today = raw.get("measurement_date", date.today())
    age = age_on(profile.birth_date, today)
    bmr_kcal = raw.get("bmr_kcal")
    if bmr_kcal is None:
        base = 10 * weight_kg + 6.25 * profile.height_cm - 5 * age
        bmr_kcal = round(base + (5 if profile.sex.lower().startswith("m") else -161))

    healthy_fat_mid, healthy_water_mid = _healthy_midpoint(profile.sex)
    metabolic_age = raw.get("metabolic_age")
    if metabolic_age is None:
        fat_penalty = max(0.0, (fat_pct or healthy_fat_mid) - healthy_fat_mid)
        bmi_penalty = max(0.0, bmi - 24.0)
        hydration_bonus = max(0.0, (water_pct or healthy_water_mid) - healthy_water_mid)
        metabolic_age = max(
            18,
            int(round(age + fat_penalty * 0.7 + bmi_penalty * 1.2 - hydration_bonus * 0.4)),
        )

    body_age = raw.get("body_age")
    if body_age is None:
        visceral_penalty = max(0.0, (raw.get("visceral_fat") or 10.0) - 12.0)
        body_age = max(18, int(round(metabolic_age + visceral_penalty * 0.5)))

    status_by_metric = classify_metrics(
        sex=profile.sex,
        bmi=bmi,
        fat_pct=fat_pct,
        water_pct=water_pct,
        visceral_fat=raw.get("visceral_fat"),
        muscle_pct=muscle_pct,
        skeletal_muscle_pct=skeletal_muscle_pct,
    )

    source_metric_map = {
        "weight_kg": raw.get("source_metric_map", {}).get("weight_kg", raw.get("source", "replay")),
        "bmi": raw.get("source_metric_map", {}).get("bmi", "computed"),
        "fat_pct": raw.get("source_metric_map", {}).get("fat_pct", raw.get("source", "replay")),
        "fat_weight_kg": raw.get("source_metric_map", {}).get("fat_weight_kg", "computed"),
        "skeletal_muscle_pct": raw.get("source_metric_map", {}).get("skeletal_muscle_pct", raw.get("source", "replay")),
        "skeletal_muscle_weight_kg": raw.get("source_metric_map", {}).get("skeletal_muscle_weight_kg", "computed"),
        "muscle_pct": raw.get("source_metric_map", {}).get("muscle_pct", raw.get("source", "replay")),
        "muscle_weight_kg": raw.get("source_metric_map", {}).get("muscle_weight_kg", "computed"),
        "visceral_fat": raw.get("source_metric_map", {}).get("visceral_fat", raw.get("source", "replay")),
        "water_pct": raw.get("source_metric_map", {}).get("water_pct", raw.get("source", "replay")),
        "water_weight_kg": raw.get("source_metric_map", {}).get("water_weight_kg", "computed"),
        "bone_weight_kg": raw.get("source_metric_map", {}).get("bone_weight_kg", "estimated"),
        "bmr_kcal": raw.get("source_metric_map", {}).get("bmr_kcal", "estimated"),
        "metabolic_age": raw.get("source_metric_map", {}).get("metabolic_age", "estimated"),
        "body_age": raw.get("source_metric_map", {}).get("body_age", "estimated"),
    }

    return {
        "measured_at": raw["measured_at"],
        "source": raw.get("source", "replay"),
        "weight_kg": weight_kg,
        "bmi": bmi,
        "fat_pct": fat_pct,
        "fat_weight_kg": fat_weight_kg,
        "skeletal_muscle_pct": skeletal_muscle_pct,
        "skeletal_muscle_weight_kg": skeletal_muscle_weight_kg,
        "muscle_pct": muscle_pct,
        "muscle_weight_kg": muscle_weight_kg,
        "visceral_fat": raw.get("visceral_fat"),
        "water_pct": water_pct,
        "water_weight_kg": water_weight_kg,
        "bone_weight_kg": bone_weight_kg,
        "bmr_kcal": bmr_kcal,
        "metabolic_age": metabolic_age,
        "body_age": body_age,
        "status_by_metric": status_by_metric,
        "source_metric_map": source_metric_map,
        "raw_payload_json": raw.get("raw_payload_json", {}),
    }


def measurement_to_chart_value(measurement: Measurement, metric: str) -> float | None:
    return getattr(measurement, metric, None)
