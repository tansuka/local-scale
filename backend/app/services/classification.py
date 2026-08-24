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


# Upper bound of Janssen's reduced-muscle-mass range, in kg/m² of skeletal
# muscle index. Janssen et al. (2004), Am J Epidemiol 159(4):413-421 defines two
# bands of elevated physical disability risk — men: <=8.50 high risk,
# 8.51-10.75 moderate risk, >10.75 normal; women: <=5.75, 5.76-6.75, >6.75. Both
# risk bands map to "low" here, since the status vocabulary has no middle term.
_SMI_REDUCED_UPPER = {"male": 10.75, "female": 6.75}


def _skeletal_muscle_mass_status(
    *,
    sex: str,
    height_cm: float | None,
    skeletal_muscle_weight_kg: float | None,
    is_estimated: bool,
) -> str:
    """Classify skeletal muscle index against Janssen's disability-risk cutpoints.

    Returns "unknown" for anthropometrically estimated muscle mass. The Lee
    (2000) equation used for that estimate is a deterministic function of
    weight, height, age and sex, so classifying its output would only restate
    BMI under a different name. Janssen's cutpoints were also derived on
    BIA-estimated muscle mass, which is not interchangeable with an
    anthropometric estimate in absolute terms.

    There is deliberately no "high" band: above-normal skeletal muscle mass is
    not a health concern.
    """
    if is_estimated:
        return "unknown"
    if skeletal_muscle_weight_kg is None or height_cm is None or height_cm <= 0:
        return "unknown"
    height_m = height_cm / 100.0
    smi = skeletal_muscle_weight_kg / (height_m**2)
    reduced_upper = _SMI_REDUCED_UPPER["male" if sex.lower().startswith("m") else "female"]
    return "low" if smi <= reduced_upper else "healthy"


def _visceral_adiposity_index_status(*, age_years: int, visceral_adiposity_index: float | None) -> str:
    if visceral_adiposity_index is None:
        return "unknown"
    if age_years < 30:
        healthy_high = 2.52
        severe_cutoff = 2.73
    elif age_years < 42:
        healthy_high = 2.23
        severe_cutoff = 3.12
    elif age_years < 52:
        healthy_high = 1.92
        severe_cutoff = 2.77
    elif age_years < 66:
        healthy_high = 1.93
        severe_cutoff = 3.25
    else:
        healthy_high = 2.00
        severe_cutoff = 3.17
    if visceral_adiposity_index <= healthy_high:
        return "healthy"
    if visceral_adiposity_index <= severe_cutoff:
        return "high"
    return "obese"


def classify_metrics(*, sex: str, age_years: int, height_cm: float | None, bmi: float | None, fat_pct: float | None, water_pct: float | None, visceral_fat: float | None, visceral_adiposity_index: float | None, muscle_pct: float | None, skeletal_muscle_weight_kg: float | None, skeletal_muscle_pct: float | None, skeletal_muscle_is_estimated: bool = False) -> dict[str, str]:
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
        "visceral_adiposity_index": _visceral_adiposity_index_status(
            age_years=age_years,
            visceral_adiposity_index=visceral_adiposity_index,
        ),
        "muscle_pct": _band(muscle_pct, *muscle_range),
        "skeletal_muscle_weight_kg": _skeletal_muscle_mass_status(
            sex=sex,
            height_cm=height_cm,
            skeletal_muscle_weight_kg=skeletal_muscle_weight_kg,
            is_estimated=skeletal_muscle_is_estimated,
        ),
        "skeletal_muscle_pct": _band(skeletal_muscle_pct, *skeletal_range),
    }
