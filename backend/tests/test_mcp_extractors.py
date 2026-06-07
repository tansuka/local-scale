"""Unit tests for MCP server extractor and helper functions.

These are pure-function tests — no database, no server, no network needed.
They validate the data-shaping logic that runs between the raw Apple Health
payload and the structured tool output.
"""
from __future__ import annotations


# Import the functions under test — the module-level side effects (engine, etc.)
# require the settings to be resolvable, so we patch minimally.
import os
os.environ.setdefault("LOCAL_SCALE_DATA_DIR", "/tmp/mcp-test-data")

from mcp_server import (  # noqa: E402
    _avg_daily,
    _extract_activity,
    _extract_body_metrics,
    _extract_heart,
    _extract_nutrition,
    _extract_sleep,
    _extract_symptoms,
    _extract_vitals,
    _extract_workouts,
    _sample_value,
)


# ── _sample_value ──────────────────────────────────────────────────────────────


def test_sample_value_extracts_numeric():
    samples = {"HKQuantityTypeIdentifierRestingHeartRate": {"value": 58}}
    assert _sample_value(samples, "HKQuantityTypeIdentifierRestingHeartRate") == 58.0


def test_sample_value_returns_none_for_missing_key():
    assert _sample_value({}, "HKQuantityTypeIdentifierRestingHeartRate") is None


def test_sample_value_returns_none_for_none_value():
    samples = {"HKQuantityTypeIdentifierRestingHeartRate": {"value": None}}
    assert _sample_value(samples, "HKQuantityTypeIdentifierRestingHeartRate") is None


# ── _avg_daily ─────────────────────────────────────────────────────────────────


def test_avg_daily_computes_average():
    daily = [
        {"date": "2026-06-01", "metrics": {"steps": 8000}},
        {"date": "2026-06-02", "metrics": {"steps": 10000}},
    ]
    assert _avg_daily(daily, "steps") == 9000.0


def test_avg_daily_returns_none_for_missing_key():
    daily = [{"date": "2026-06-01", "metrics": {"steps": 8000}}]
    assert _avg_daily(daily, "calories") is None


def test_avg_daily_skips_none_values():
    daily = [
        {"date": "2026-06-01", "metrics": {"steps": 8000}},
        {"date": "2026-06-02", "metrics": {"steps": None}},
    ]
    assert _avg_daily(daily, "steps") == 8000.0


def test_avg_daily_handles_non_numeric_gracefully():
    daily = [
        {"date": "2026-06-01", "metrics": {"steps": 8000}},
        {"date": "2026-06-02", "metrics": {"steps": "not_a_number"}},
    ]
    # Should skip the bad value, average only the valid one
    assert _avg_daily(daily, "steps") == 8000.0


def test_avg_daily_empty_summaries():
    assert _avg_daily([], "steps") is None


def test_avg_daily_handles_missing_metrics_key():
    daily = [{"date": "2026-06-01"}]  # no "metrics" key
    assert _avg_daily(daily, "steps") is None


# ── _extract_activity ──────────────────────────────────────────────────────────


def test_extract_activity_basic():
    payload = {
        "daily_summaries": [
            {
                "date": "2026-06-01",
                "metrics": {
                    "HKQuantityTypeIdentifierStepCount": 9000,
                    "HKQuantityTypeIdentifierActiveEnergyBurned": 400,
                    "HKQuantityTypeIdentifierAppleExerciseTime": 35,
                },
            }
        ]
    }
    result = _extract_activity(payload)
    assert result["days_in_period"] == 1
    assert result["steps_avg"] == 9000.0
    assert result["active_energy_kcal_avg"] == 400.0
    assert result["exercise_minutes_avg"] == 35.0


def test_extract_activity_empty_payload():
    result = _extract_activity({})
    assert result["days_in_period"] == 0
    assert result["steps_avg"] is None


# ── _extract_heart ─────────────────────────────────────────────────────────────


def test_extract_heart_basic():
    payload = {
        "latest_samples": {
            "HKQuantityTypeIdentifierRestingHeartRate": {"value": 55},
            "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": {"value": 42},
            "HKQuantityTypeIdentifierOxygenSaturation": {"value": 0.98},
        }
    }
    result = _extract_heart(payload)
    assert result["resting_hr_bpm"] == 55.0
    assert result["hrv_sdnn_ms"] == 42.0
    assert result["oxygen_saturation_pct"] == 98.0


def test_extract_heart_with_ecg():
    payload = {
        "latest_samples": {},
        "ecg_readings": [
            {"classification": "sinusRhythm", "average_heart_rate": 72, "start_date": "2026-06-07"}
        ],
    }
    result = _extract_heart(payload)
    assert result["latest_ecg"]["classification"] == "sinusRhythm"
    assert result["latest_ecg"]["avg_hr_bpm"] == 72


def test_extract_heart_no_ecg():
    payload = {"latest_samples": {}}
    result = _extract_heart(payload)
    assert result["latest_ecg"] is None


# ── _extract_sleep ─────────────────────────────────────────────────────────────


def test_extract_sleep_basic():
    payload = {
        "recent_events": {
            "HKCategoryTypeIdentifierSleepAnalysis": [
                {
                    "description": "asleepCore",
                    "start_date": "2026-06-07T00:00:00+00:00",
                    "end_date": "2026-06-07T03:00:00+00:00",
                },
                {
                    "description": "asleepDeep",
                    "start_date": "2026-06-07T03:00:00+00:00",
                    "end_date": "2026-06-07T04:30:00+00:00",
                },
                {
                    "description": "asleepREM",
                    "start_date": "2026-06-07T04:30:00+00:00",
                    "end_date": "2026-06-07T06:00:00+00:00",
                },
            ]
        }
    }
    result = _extract_sleep(payload)
    assert result is not None
    assert result["total_sleep_hours"] == 6.0
    assert result["below_7h"] is True
    assert len(result["sessions"]) == 3


def test_extract_sleep_returns_none_when_absent():
    assert _extract_sleep({}) is None
    assert _extract_sleep({"recent_events": {}}) is None


# ── _extract_nutrition ─────────────────────────────────────────────────────────


def test_extract_nutrition_basic():
    payload = {
        "daily_summaries": [
            {
                "date": "2026-06-01",
                "metrics": {
                    "HKQuantityTypeIdentifierDietaryEnergyConsumed": 2200,
                    "HKQuantityTypeIdentifierDietaryProtein": 120,
                },
            }
        ]
    }
    result = _extract_nutrition(payload)
    assert result["calories_kcal_avg"] == 2200.0
    assert result["protein_g_avg"] == 120.0


# ── _extract_vitals ────────────────────────────────────────────────────────────


def test_extract_vitals_basic():
    payload = {
        "latest_samples": {
            "HKQuantityTypeIdentifierBodyTemperature": {"value": 36.6},
            "HKQuantityTypeIdentifierRespiratoryRate": {"value": 15},
        }
    }
    result = _extract_vitals(payload)
    assert result["body_temp_c"] == 36.6
    assert result["respiratory_rate_breaths_min"] == 15.0


# ── _extract_body_metrics ─────────────────────────────────────────────────────


def test_extract_body_metrics_converts_fat_ratio():
    payload = {
        "latest_samples": {
            "HKQuantityTypeIdentifierBodyFatPercentage": {"value": 0.165},
            "HKQuantityTypeIdentifierBodyMass": {"value": 80.0},
        }
    }
    result = _extract_body_metrics(payload)
    assert result["body_fat_pct"] == 16.5
    assert result["weight_kg"] == 80.0


def test_extract_body_metrics_none_fat():
    payload = {"latest_samples": {}}
    result = _extract_body_metrics(payload)
    assert result["body_fat_pct"] is None


# ── _extract_workouts ──────────────────────────────────────────────────────────


def test_extract_workouts_basic():
    payload = {
        "workouts": [
            {
                "type": "running",
                "start_date": "2026-06-07T07:00:00Z",
                "end_date": "2026-06-07T07:45:00Z",
                "duration_minutes": 45,
                "energy_burned_kcal": 450,
                "distance_meters": 7500,
            }
        ]
    }
    result = _extract_workouts(payload)
    assert len(result) == 1
    assert result[0]["type"] == "running"
    assert result[0]["duration_minutes"] == 45
    assert result[0]["energy_kcal"] == 450


def test_extract_workouts_empty():
    assert _extract_workouts({}) == []


# ── _extract_symptoms ──────────────────────────────────────────────────────────


def test_extract_symptoms_filters_not_present():
    payload = {
        "recent_events": {
            "HKCategoryTypeIdentifierFatigue": [
                {"description": "mild", "start_date": "2026-06-07T08:00:00Z", "end_date": "2026-06-07T12:00:00Z"},
            ],
            "HKCategoryTypeIdentifierHeadache": [
                {"description": "notPresent", "start_date": "2026-06-07T08:00:00Z", "end_date": "2026-06-07T12:00:00Z"},
            ],
        }
    }
    result = _extract_symptoms(payload)
    assert len(result) == 1
    assert result[0]["symptom"] == "fatigue"
    assert result[0]["severity"] == "mild"


def test_extract_symptoms_empty():
    assert _extract_symptoms({}) == []
