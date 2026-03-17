from __future__ import annotations

from statistics import median

from app.models import Measurement


def anomaly_score(recent_measurements: list[Measurement], candidate: dict) -> float:
    if len(recent_measurements) < 3:
        return 0.0

    weights = [item.weight_kg for item in recent_measurements]
    center = median(weights)
    deviations = [abs(value - center) for value in weights]
    mad = median(deviations) or 0.45
    weight_score = min(
        1.0,
        abs(candidate["weight_kg"] - center) / max(mad * 4.5, 2.0),
    )

    fat_values = [item.fat_pct for item in recent_measurements if item.fat_pct is not None]
    fat_score = 0.0
    if fat_values and candidate.get("fat_pct") is not None:
        fat_center = median(fat_values)
        fat_score = min(1.0, abs(candidate["fat_pct"] - fat_center) / 7.5)

    return round(weight_score * 0.75 + fat_score * 0.25, 3)


def requires_confirmation(score: float, candidate: dict, recent_measurements: list[Measurement]) -> bool:
    if len(recent_measurements) < 3:
        return True
    recent_weight = median([item.weight_kg for item in recent_measurements])
    return score >= 0.65 or abs(candidate["weight_kg"] - recent_weight) >= 4.5
