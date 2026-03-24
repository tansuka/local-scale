from __future__ import annotations


def _band(value: float | None, healthy_low: float, healthy_high: float) -> str:
    if value is None:
        return "unknown"
    if value < healthy_low * 0.8:
        return "low"
    if value < healthy_low:
        return "low"
    if value <= healthy_high:
        return "healthy"
    if value <= healthy_high * 1.2:
        return "high"
    return "obese"


def _skeletal_muscle_mass_status(
    *,
    sex: str,
    height_cm: float | None,
    skeletal_muscle_weight_kg: float | None,
) -> str:
    if skeletal_muscle_weight_kg is None or height_cm is None or height_cm <= 0:
        return "unknown"
    height_m = height_cm / 100.0
    smi = skeletal_muscle_weight_kg / (height_m**2)
    if sex.lower().startswith("m"):
        low_cutoff = 8.5
        healthy_high = 10.75
    else:
        low_cutoff = 5.75
        healthy_high = 6.75
    if smi <= low_cutoff:
        return "low"
    if smi <= healthy_high:
        return "healthy"
    return "high"


def classify_metrics(*, sex: str, height_cm: float | None, bmi: float | None, fat_pct: float | None, water_pct: float | None, visceral_fat: float | None, muscle_pct: float | None, skeletal_muscle_weight_kg: float | None, skeletal_muscle_pct: float | None) -> dict[str, str]:
    if sex.lower().startswith("m"):
        fat_range = (8.0, 20.0)
        water_range = (50.0, 65.0)
        muscle_range = (38.0, 50.0)
        skeletal_range = (40.0, 52.0)
    else:
        fat_range = (21.0, 33.0)
        water_range = (45.0, 60.0)
        muscle_range = (28.0, 40.0)
        skeletal_range = (30.0, 41.0)

    return {
        "bmi": _band(bmi, 18.5, 24.9),
        "fat_pct": _band(fat_pct, *fat_range),
        "water_pct": _band(water_pct, *water_range),
        "visceral_fat": _band(visceral_fat, 1.0, 12.0),
        "muscle_pct": _band(muscle_pct, *muscle_range),
        "skeletal_muscle_weight_kg": _skeletal_muscle_mass_status(
            sex=sex,
            height_cm=height_cm,
            skeletal_muscle_weight_kg=skeletal_muscle_weight_kg,
        ),
        "skeletal_muscle_pct": _band(skeletal_muscle_pct, *skeletal_range),
    }
