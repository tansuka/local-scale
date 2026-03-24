from __future__ import annotations

from datetime import date, datetime, timezone

from app.models import Profile
from app.services.anthropometric import (
    estimate_fat_pct,
    estimate_skeletal_muscle_mass_kg,
    estimate_total_body_water_kg,
    estimate_water_pct,
    measurement_date_from_raw,
)


def test_estimate_fat_pct_for_adult_male_uses_deurenberg_1992():
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

    fat_pct = estimate_fat_pct(
        profile=profile,
        weight_kg=74.19,
        measurement_date=date(2026, 3, 17),
    )

    assert fat_pct == 19.56


def test_estimate_fat_pct_for_adult_female_uses_deurenberg_1992():
    profile = Profile(
        id=1,
        name="Casey",
        sex="female",
        birth_date=date(1992, 7, 14),
        height_cm=168,
        units="metric",
        color="#0f766e",
        active=True,
    )

    fat_pct = estimate_fat_pct(
        profile=profile,
        weight_kg=61.0,
        measurement_date=date(2026, 3, 17),
    )

    assert fat_pct == 28.13


def test_estimate_fat_pct_for_under_16_profile_uses_child_branch():
    profile = Profile(
        id=1,
        name="Sam",
        sex="male",
        birth_date=date(2012, 9, 1),
        height_cm=158,
        units="metric",
        color="#0f766e",
        active=True,
    )

    fat_pct = estimate_fat_pct(
        profile=profile,
        weight_kg=50.0,
        measurement_date=date(2026, 3, 17),
    )

    assert fat_pct == 9.12


def test_estimate_water_pct_uses_hume_weyers_formula():
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

    total_body_water_kg = estimate_total_body_water_kg(profile=profile, weight_kg=74.19)
    water_pct = estimate_water_pct(profile=profile, weight_kg=74.19)

    assert round(total_body_water_kg, 3) == 43.067
    assert water_pct == 58.05


def test_estimate_skeletal_muscle_mass_uses_lee_equation_without_race_adjustment():
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

    skeletal_muscle_mass = estimate_skeletal_muscle_mass_kg(
        profile=profile,
        weight_kg=74.19,
        measurement_date=date(2026, 3, 17),
    )

    assert skeletal_muscle_mass == 31.91


def test_measurement_date_from_raw_prefers_measured_at_when_missing_explicit_date():
    assert measurement_date_from_raw(
        {"measured_at": datetime(2025, 12, 1, 7, 30, tzinfo=timezone.utc)}
    ) == date(2025, 12, 1)
