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
    _sample_date,
    _sample_value,
    _sample_with_date,
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


# ── _sample_date ───────────────────────────────────────────────────────────────


def test_sample_date_extracts_date_field():
    samples = {"key": {"value": 58, "date": "2026-06-05T08:30:00Z"}}
    assert _sample_date(samples, "key") == "2026-06-05T08:30:00Z"


def test_sample_date_falls_back_to_start_date():
    samples = {"key": {"value": 58, "start_date": "2026-06-04T10:00:00Z"}}
    assert _sample_date(samples, "key") == "2026-06-04T10:00:00Z"


def test_sample_date_prefers_date_over_start_date():
    samples = {"key": {"value": 58, "date": "2026-06-05", "start_date": "2026-06-04"}}
    assert _sample_date(samples, "key") == "2026-06-05"


def test_sample_date_returns_none_when_no_dates():
    samples = {"key": {"value": 58}}
    assert _sample_date(samples, "key") is None


def test_sample_date_returns_none_for_missing_key():
    assert _sample_date({}, "key") is None


# ── _sample_with_date ──────────────────────────────────────────────────────────


def test_sample_with_date_returns_value_and_measured_at():
    samples = {"key": {"value": 36.6, "date": "2026-06-05T07:00:00Z"}}
    result = _sample_with_date(samples, "key")
    assert result == {"value": 36.6, "measured_at": "2026-06-05T07:00:00Z"}


def test_sample_with_date_omits_measured_at_when_no_date():
    samples = {"key": {"value": 36.6}}
    result = _sample_with_date(samples, "key")
    assert result == {"value": 36.6}


def test_sample_with_date_returns_none_for_missing_key():
    assert _sample_with_date({}, "key") is None


def test_sample_with_date_returns_none_for_none_value():
    samples = {"key": {"value": None, "date": "2026-06-05"}}
    assert _sample_with_date(samples, "key") is None


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
    assert result["steps"] == 9000.0
    assert result["active_energy_kcal"] == 400.0
    assert result["exercise_min"] == 35.0


def test_extract_activity_empty_payload():
    result = _extract_activity({})
    assert result["steps"] is None


# ── _extract_heart ─────────────────────────────────────────────────────────────


def test_extract_heart_basic():
    payload = {
        "latest_samples": {
            "HKQuantityTypeIdentifierRestingHeartRate": {
                "value": 55, "date": "2026-06-05T06:00:00Z",
            },
            "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": {
                "value": 42, "date": "2026-06-05T06:00:00Z",
            },
            "HKQuantityTypeIdentifierOxygenSaturation": {
                "value": 0.98, "date": "2026-06-04T23:00:00Z",
            },
        }
    }
    result = _extract_heart(payload)
    assert result["resting_hr"]["value"] == 55.0
    assert result["resting_hr"]["measured_at"] == "2026-06-05T06:00:00Z"
    assert result["hrv_sdnn"]["value"] == 42.0
    assert result["oxygen_saturation_pct"]["value"] == 98.0
    assert result["oxygen_saturation_pct"]["measured_at"] == "2026-06-04T23:00:00Z"


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
    assert result["latest_ecg"]["measured_at"] == "2026-06-07"


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
    assert result["total_hours"] == 6.0
    assert result["below_7h"] is True
    assert result["stages_min"]["asleepCore"] == 180.0
    assert result["stages_min"]["asleepDeep"] == 90.0
    assert result["stages_min"]["asleepREM"] == 90.0


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
    assert result["calories_kcal"] == 2200.0
    assert result["protein_g"] == 120.0


# ── _extract_vitals ────────────────────────────────────────────────────────────


def test_extract_vitals_basic():
    payload = {
        "latest_samples": {
            "HKQuantityTypeIdentifierBodyTemperature": {
                "value": 36.6, "date": "2026-06-06T08:00:00Z",
            },
            "HKQuantityTypeIdentifierRespiratoryRate": {
                "value": 15, "start_date": "2026-06-06T07:30:00Z",
            },
        }
    }
    result = _extract_vitals(payload)
    assert result["body_temp_c"]["value"] == 36.6
    assert result["body_temp_c"]["measured_at"] == "2026-06-06T08:00:00Z"
    assert result["respiratory_rate"]["value"] == 15.0
    assert result["respiratory_rate"]["measured_at"] == "2026-06-06T07:30:00Z"


# ── _extract_body_metrics ─────────────────────────────────────────────────────


def test_extract_body_metrics_converts_fat_ratio():
    payload = {
        "latest_samples": {
            "HKQuantityTypeIdentifierBodyFatPercentage": {
                "value": 0.165, "date": "2026-06-05T07:15:00Z",
            },
            "HKQuantityTypeIdentifierBodyMass": {
                "value": 80.0, "date": "2026-06-05T07:15:00Z",
            },
        }
    }
    result = _extract_body_metrics(payload)
    assert result["body_fat_pct"]["value"] == 16.5
    assert result["body_fat_pct"]["measured_at"] == "2026-06-05T07:15:00Z"
    assert result["weight_kg"]["value"] == 80.0


def test_extract_body_metrics_none_fat():
    payload = {"latest_samples": {}}
    result = _extract_body_metrics(payload)
    assert result["body_fat_pct"] is None
    assert result["weight_kg"] is None


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
    assert result[0]["dur_min"] == 45
    assert result[0]["kcal"] == 450


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
