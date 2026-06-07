"""
Apple Health MCP Server — exposes synced Apple Health data via HTTP/SSE.

Run:
    python backend/mcp_server.py

Agent MCP config:
    {
      "mcpServers": {
        "local-scale-health": {
          "url": "http://<minipc-ip>:8001/sse"
        }
      }
    }

Environment variables:
    LOCAL_SCALE_DATABASE_URL  — SQLite URL (default: same as FastAPI app)
    LOCAL_SCALE_MCP_PORT      — Port to bind (default: 8001)
    LOCAL_SCALE_MCP_HOST      — Host to bind (default: 0.0.0.0)
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure the backend package is importable when running this file directly
sys.path.insert(0, str(Path(__file__).parent))

import uvicorn
from mcp import types
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Mount, Route

from app.core.config import get_settings
from app.repositories.apple_health import get_latest_snapshot, list_snapshot_metadata

# ── Database (read-only connection to the same SQLite as FastAPI) ──────────────

_settings = get_settings()
_engine = create_engine(
    _settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in _settings.database_url else {},
)
_SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)


def _db() -> Session:
    return _SessionLocal()


# ── MCP server instance ────────────────────────────────────────────────────────

server = Server("local-scale-health")


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _data_age_hours(captured_at: datetime) -> float:
    now = datetime.now(timezone.utc)
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=timezone.utc)
    return round((now - captured_at).total_seconds() / 3600, 1)


def _sample_value(samples: dict, hk_key: str) -> float | None:
    """Extract the numeric value from a latest_samples entry."""
    entry = samples.get(hk_key)
    if entry and isinstance(entry, dict):
        val = entry.get("value")
        return float(val) if val is not None else None
    return None


def _avg_daily(daily_summaries: list[dict], hk_key: str) -> float | None:
    """Average a metric across all days in daily_summaries."""
    values = [
        float(d["metrics"][hk_key])
        for d in daily_summaries
        if hk_key in d.get("metrics", {}) and d["metrics"][hk_key] is not None
    ]
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _ok(data: dict) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=json.dumps(data, default=str))]


def _no_snapshot(profile_id: int) -> list[types.TextContent]:
    return _ok({"error": f"No Apple Health snapshot found for profile_id={profile_id}."})


def _snapshot_meta(snapshot: Any) -> dict:
    return {
        "profile_id": snapshot.profile_id,
        "captured_at": snapshot.captured_at.isoformat(),
        "period_start": snapshot.period_start.isoformat(),
        "period_end": snapshot.period_end.isoformat(),
        "data_age_hours": _data_age_hours(snapshot.captured_at),
    }


# ── Category extractors ────────────────────────────────────────────────────────

def _extract_activity(payload: dict) -> dict:
    daily = payload.get("daily_summaries", [])
    return {
        "days_in_period": len(daily),
        "steps_avg": _avg_daily(daily, "HKQuantityTypeIdentifierStepCount"),
        "active_energy_kcal_avg": _avg_daily(daily, "HKQuantityTypeIdentifierActiveEnergyBurned"),
        "basal_energy_kcal_avg": _avg_daily(daily, "HKQuantityTypeIdentifierBasalEnergyBurned"),
        "exercise_minutes_avg": _avg_daily(daily, "HKQuantityTypeIdentifierAppleExerciseTime"),
        "distance_walking_m_avg": _avg_daily(daily, "HKQuantityTypeIdentifierDistanceWalkingRunning"),
        "distance_cycling_m_avg": _avg_daily(daily, "HKQuantityTypeIdentifierDistanceCycling"),
        "distance_swimming_m_avg": _avg_daily(daily, "HKQuantityTypeIdentifierDistanceSwimming"),
        "flights_climbed_avg": _avg_daily(daily, "HKQuantityTypeIdentifierFlightsClimbed"),
        "stand_minutes_avg": _avg_daily(daily, "HKQuantityTypeIdentifierAppleStandTime"),
        "move_minutes_avg": _avg_daily(daily, "HKQuantityTypeIdentifierAppleMoveTime"),
        "time_in_daylight_min_avg": _avg_daily(daily, "HKQuantityTypeIdentifierTimeInDaylight"),
    }


def _extract_heart(payload: dict) -> dict:
    samples = payload.get("latest_samples", {})

    # O2 saturation is stored as a ratio (0.98), convert to percentage
    o2_raw = _sample_value(samples, "HKQuantityTypeIdentifierOxygenSaturation")
    o2_pct = round(o2_raw * 100, 1) if o2_raw is not None else None

    # Latest ECG summary
    ecg_readings = payload.get("ecg_readings", [])
    latest_ecg: dict | None = None
    if ecg_readings:
        ecg = ecg_readings[-1]
        latest_ecg = {
            "classification": ecg.get("classification"),
            "avg_hr_bpm": ecg.get("average_heart_rate"),
            "date": ecg.get("start_date"),
        }

    return {
        "resting_hr_bpm": _sample_value(samples, "HKQuantityTypeIdentifierRestingHeartRate"),
        "hrv_sdnn_ms": _sample_value(samples, "HKQuantityTypeIdentifierHeartRateVariabilitySDNN"),
        "walking_hr_avg_bpm": _sample_value(samples, "HKQuantityTypeIdentifierWalkingHeartRateAverage"),
        "hr_recovery_1min_bpm": _sample_value(samples, "HKQuantityTypeIdentifierHeartRateRecoveryOneMinute"),
        "vo2_max_ml_kg_min": _sample_value(samples, "HKQuantityTypeIdentifierVo2Max"),
        "oxygen_saturation_pct": o2_pct,
        "blood_pressure_systolic_mmhg": _sample_value(samples, "HKQuantityTypeIdentifierBloodPressureSystolic"),
        "blood_pressure_diastolic_mmhg": _sample_value(samples, "HKQuantityTypeIdentifierBloodPressureDiastolic"),
        "afib_burden_pct": _sample_value(samples, "HKQuantityTypeIdentifierAtrialFibrillationBurden"),
        "latest_ecg": latest_ecg,
    }


def _extract_sleep(payload: dict) -> dict | None:
    """
    Extracts sleep data from recent_events.HKCategoryTypeIdentifierSleepAnalysis.
    Returns None if sleep data is not present in the snapshot.
    Sleep stage descriptions: asleep, asleepCore, asleepDeep, asleepREM, awake, inBed.
    """
    events = payload.get("recent_events", {})
    sleep_events = events.get("HKCategoryTypeIdentifierSleepAnalysis", [])
    if not sleep_events:
        return None

    asleep_stages = {"asleep", "asleepCore", "asleepDeep", "asleepREM"}
    total_asleep_min = 0.0
    sessions: list[dict] = []

    for e in sleep_events:
        start = e.get("start_date")
        end = e.get("end_date")
        desc = e.get("description", "unknown")
        duration_min = 0.0
        if start and end:
            try:
                s = datetime.fromisoformat(start.replace("Z", "+00:00"))
                en = datetime.fromisoformat(end.replace("Z", "+00:00"))
                duration_min = (en - s).total_seconds() / 60
            except Exception:
                pass
        if desc in asleep_stages:
            total_asleep_min += duration_min
        sessions.append({
            "stage": desc,
            "start": start,
            "end": end,
            "duration_minutes": round(duration_min, 1),
        })

    total_hours = round(total_asleep_min / 60, 2)
    return {
        "total_sleep_hours": total_hours,
        "below_7h": total_hours < 7.0,
        "sessions": sessions,
    }


def _extract_nutrition(payload: dict) -> dict:
    daily = payload.get("daily_summaries", [])
    return {
        "days_in_period": len(daily),
        "calories_kcal_avg": _avg_daily(daily, "HKQuantityTypeIdentifierDietaryEnergyConsumed"),
        "water_L_avg": _avg_daily(daily, "HKQuantityTypeIdentifierDietaryWater"),
        "protein_g_avg": _avg_daily(daily, "HKQuantityTypeIdentifierDietaryProtein"),
        "carbs_g_avg": _avg_daily(daily, "HKQuantityTypeIdentifierDietaryCarbohydrates"),
        "fat_total_g_avg": _avg_daily(daily, "HKQuantityTypeIdentifierDietaryFatTotal"),
        "fat_saturated_g_avg": _avg_daily(daily, "HKQuantityTypeIdentifierDietaryFatSaturated"),
        "fat_monounsaturated_g_avg": _avg_daily(daily, "HKQuantityTypeIdentifierDietaryFatMonounsaturated"),
        "fat_polyunsaturated_g_avg": _avg_daily(daily, "HKQuantityTypeIdentifierDietaryFatPolyunsaturated"),
        "fiber_g_avg": _avg_daily(daily, "HKQuantityTypeIdentifierDietaryFiber"),
        "sugar_g_avg": _avg_daily(daily, "HKQuantityTypeIdentifierDietarySugar"),
        "sodium_g_avg": _avg_daily(daily, "HKQuantityTypeIdentifierDietarySodium"),
        "caffeine_g_avg": _avg_daily(daily, "HKQuantityTypeIdentifierDietaryCaffeine"),
        "alcohol_drinks_avg": _avg_daily(daily, "HKQuantityTypeIdentifierNumberOfAlcoholicBeverages"),
        "cholesterol_g_avg": _avg_daily(daily, "HKQuantityTypeIdentifierDietaryCholesterol"),
    }


def _extract_vitals(payload: dict) -> dict:
    samples = payload.get("latest_samples", {})
    return {
        "body_temp_c": _sample_value(samples, "HKQuantityTypeIdentifierBodyTemperature"),
        "wrist_temp_c": _sample_value(samples, "HKQuantityTypeIdentifierAppleSleepingWristTemperature"),
        "basal_body_temp_c": _sample_value(samples, "HKQuantityTypeIdentifierBasalBodyTemperature"),
        "respiratory_rate_breaths_min": _sample_value(samples, "HKQuantityTypeIdentifierRespiratoryRate"),
        "blood_glucose_mg_dl": _sample_value(samples, "HKQuantityTypeIdentifierBloodGlucose"),
        "blood_alcohol_pct": _sample_value(samples, "HKQuantityTypeIdentifierBloodAlcoholContent"),
    }


def _extract_body_metrics(payload: dict) -> dict:
    samples = payload.get("latest_samples", {})
    # Body fat is stored as a ratio (0.165 = 16.5%) — convert to percentage
    fat_raw = _sample_value(samples, "HKQuantityTypeIdentifierBodyFatPercentage")
    fat_pct = round(fat_raw * 100, 1) if fat_raw is not None else None
    return {
        "weight_kg": _sample_value(samples, "HKQuantityTypeIdentifierBodyMass"),
        "body_fat_pct": fat_pct,
        "bmi": _sample_value(samples, "HKQuantityTypeIdentifierBodyMassIndex"),
        "lean_mass_kg": _sample_value(samples, "HKQuantityTypeIdentifierLeanBodyMass"),
        "waist_cm": _sample_value(samples, "HKQuantityTypeIdentifierWaistCircumference"),
        "height_m": _sample_value(samples, "HKQuantityTypeIdentifierHeight"),
    }


def _extract_workouts(payload: dict) -> list[dict]:
    return [
        {
            "type": w.get("type"),
            "start": w.get("start_date"),
            "end": w.get("end_date"),
            "duration_minutes": w.get("duration_minutes"),
            "energy_kcal": w.get("energy_burned_kcal"),
            "distance_m": w.get("distance_meters"),
        }
        for w in payload.get("workouts", [])
    ]


# Symptom categories we care about — maps HK key → human-readable label
_SYMPTOM_KEYS: dict[str, str] = {
    "HKCategoryTypeIdentifierFatigue": "fatigue",
    "HKCategoryTypeIdentifierHeadache": "headache",
    "HKCategoryTypeIdentifierAbdominalCramps": "abdominal_cramps",
    "HKCategoryTypeIdentifierBloating": "bloating",
    "HKCategoryTypeIdentifierNausea": "nausea",
    "HKCategoryTypeIdentifierVomiting": "vomiting",
    "HKCategoryTypeIdentifierDizziness": "dizziness",
    "HKCategoryTypeIdentifierFainting": "fainting",
    "HKCategoryTypeIdentifierFever": "fever",
    "HKCategoryTypeIdentifierChills": "chills",
    "HKCategoryTypeIdentifierChestTightnessOrPain": "chest_pain",
    "HKCategoryTypeIdentifierShortnessOfBreath": "shortness_of_breath",
    "HKCategoryTypeIdentifierSkippedHeartbeat": "skipped_heartbeat",
    "HKCategoryTypeIdentifierRapidPoundingOrFlutteringHeartbeat": "palpitations",
    "HKCategoryTypeIdentifierLowerBackPain": "lower_back_pain",
    "HKCategoryTypeIdentifierGeneralizedBodyAche": "body_ache",
    "HKCategoryTypeIdentifierCoughing": "coughing",
    "HKCategoryTypeIdentifierWheezing": "wheezing",
    "HKCategoryTypeIdentifierSleepChanges": "sleep_changes",
    "HKCategoryTypeIdentifierMoodChanges": "mood_changes",
    "HKCategoryTypeIdentifierMemoryLapse": "memory_lapse",
    "HKCategoryTypeIdentifierNightSweats": "night_sweats",
    "HKCategoryTypeIdentifierHotFlashes": "hot_flashes",
    "HKCategoryTypeIdentifierLossOfSmell": "loss_of_smell",
    "HKCategoryTypeIdentifierLossOfTaste": "loss_of_taste",
    "HKCategoryTypeIdentifierSoreThroat": "sore_throat",
    "HKCategoryTypeIdentifierRunnyNose": "runny_nose",
    "HKCategoryTypeIdentifierSinusCongestion": "sinus_congestion",
    "HKCategoryTypeIdentifierAcne": "acne",
    "HKCategoryTypeIdentifierHairLoss": "hair_loss",
}


def _extract_symptoms(payload: dict) -> list[dict]:
    """Return only active/present symptoms (filters out notPresent entries)."""
    events = payload.get("recent_events", {})
    active: list[dict] = []
    for hk_key, label in _SYMPTOM_KEYS.items():
        entries = events.get(hk_key, [])
        for e in entries:
            if e.get("description") == "notPresent":
                continue
            active.append({
                "symptom": label,
                "severity": e.get("description", "unknown"),
                "start": e.get("start_date"),
                "end": e.get("end_date"),
            })
    return active


# ── Tool definitions ───────────────────────────────────────────────────────────

_PROFILE_ID_SCHEMA = {
    "type": "object",
    "properties": {
        "profile_id": {
            "type": "integer",
            "description": "The local-scale profile ID to fetch data for.",
        }
    },
    "required": ["profile_id"],
}

TOOLS: list[types.Tool] = [
    types.Tool(
        name="get_apple_health_context",
        description=(
            "Returns a complete LLM-ready overview of the latest Apple Health snapshot for a profile. "
            "Includes activity, heart, sleep, nutrition, vitals, body metrics, workouts, and active symptoms. "
            "Use this for initial health context injection into your reasoning."
        ),
        inputSchema=_PROFILE_ID_SCHEMA,
    ),
    types.Tool(
        name="get_activity",
        description=(
            "Returns daily activity metrics averaged across the snapshot period: "
            "steps, active & basal energy, exercise minutes, walking/cycling/swimming distance, "
            "flights climbed, stand time, move time, time in daylight."
        ),
        inputSchema=_PROFILE_ID_SCHEMA,
    ),
    types.Tool(
        name="get_heart",
        description=(
            "Returns heart health data from the latest Apple Health snapshot: "
            "resting HR, HRV (SDNN), walking HR average, 1-min HR recovery, VO2 max, "
            "oxygen saturation, blood pressure, AFib burden, and latest ECG classification."
        ),
        inputSchema=_PROFILE_ID_SCHEMA,
    ),
    types.Tool(
        name="get_sleep",
        description=(
            "Returns sleep data from the latest Apple Health snapshot: "
            "total sleep hours, stage breakdown (core/deep/REM/awake), and whether the user slept under 7 hours. "
            "Returns a note if the snapshot does not include sleep data yet."
        ),
        inputSchema=_PROFILE_ID_SCHEMA,
    ),
    types.Tool(
        name="get_nutrition",
        description=(
            "Returns dietary intake averaged across the snapshot period: "
            "calories, water, protein, carbs, all fat types, fiber, sugar, sodium, caffeine, and alcohol drinks."
        ),
        inputSchema=_PROFILE_ID_SCHEMA,
    ),
    types.Tool(
        name="get_vitals",
        description=(
            "Returns vital sign readings from the latest Apple Health snapshot: "
            "body temperature, wrist temperature, respiratory rate, blood glucose, blood alcohol."
        ),
        inputSchema=_PROFILE_ID_SCHEMA,
    ),
    types.Tool(
        name="get_body_metrics",
        description=(
            "Returns body composition metrics recorded in Apple Health: "
            "weight, body fat %, BMI, lean mass, waist circumference, height. "
            "Note: these are Apple Health readings — for scale BIA body composition use the scale measurement tools."
        ),
        inputSchema=_PROFILE_ID_SCHEMA,
    ),
    types.Tool(
        name="get_workouts",
        description=(
            "Returns the list of workout sessions recorded in the latest Apple Health snapshot: "
            "type, start/end time, duration, calories burned, and distance."
        ),
        inputSchema=_PROFILE_ID_SCHEMA,
    ),
    types.Tool(
        name="get_symptoms",
        description=(
            "Returns active or recently recorded symptoms from Apple Health "
            "(e.g. fatigue, headache, chest pain, nausea) with severity level and time window. "
            "Returns an empty list if no symptoms are present. "
            "notPresent entries are filtered out automatically."
        ),
        inputSchema=_PROFILE_ID_SCHEMA,
    ),
    types.Tool(
        name="get_snapshots_list",
        description=(
            "Returns a lightweight list of available Apple Health snapshots for a profile "
            "(id, captured_at, period_start, period_end) without loading payload data. "
            "Useful for checking data freshness before calling a heavier tool."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "profile_id": {
                    "type": "integer",
                    "description": "The local-scale profile ID.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of snapshots to return (default 10, max 90).",
                    "default": 10,
                },
            },
            "required": ["profile_id"],
        },
    ),
]


# ── Tool handlers ──────────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    profile_id: int = int(arguments["profile_id"])

    # Metadata-only tool — no payload needed
    if name == "get_snapshots_list":
        limit = min(int(arguments.get("limit", 10)), 90)
        db = _db()
        try:
            rows = list_snapshot_metadata(db, profile_id, limit=limit)
        finally:
            db.close()
        return _ok({"profile_id": profile_id, "count": len(rows), "snapshots": rows})

    # All other tools need the latest snapshot payload
    db = _db()
    try:
        snapshot = get_latest_snapshot(db, profile_id)
    finally:
        db.close()

    if snapshot is None:
        return _no_snapshot(profile_id)

    payload = snapshot.payload_json or {}
    meta = _snapshot_meta(snapshot)

    match name:
        case "get_apple_health_context":
            sleep = _extract_sleep(payload)
            return _ok({
                **meta,
                "activity": _extract_activity(payload),
                "heart": _extract_heart(payload),
                "sleep": sleep or {"note": "Sleep data not present in this snapshot."},
                "nutrition": _extract_nutrition(payload),
                "vitals": _extract_vitals(payload),
                "body_metrics": _extract_body_metrics(payload),
                "workouts": _extract_workouts(payload),
                "symptoms": _extract_symptoms(payload),
            })
        case "get_activity":
            return _ok({**meta, "activity": _extract_activity(payload)})
        case "get_heart":
            return _ok({**meta, "heart": _extract_heart(payload)})
        case "get_sleep":
            sleep = _extract_sleep(payload)
            return _ok({
                **meta,
                "sleep": sleep or {
                    "note": "Sleep data (HKCategoryTypeIdentifierSleepAnalysis) not present in this snapshot."
                },
            })
        case "get_nutrition":
            return _ok({**meta, "nutrition": _extract_nutrition(payload)})
        case "get_vitals":
            return _ok({**meta, "vitals": _extract_vitals(payload)})
        case "get_body_metrics":
            return _ok({**meta, "body_metrics": _extract_body_metrics(payload)})
        case "get_workouts":
            return _ok({**meta, "workouts": _extract_workouts(payload)})
        case "get_symptoms":
            return _ok({**meta, "symptoms": _extract_symptoms(payload)})
        case _:
            return _ok({"error": f"Unknown tool: {name}"})


# ── SSE transport + Starlette app ──────────────────────────────────────────────

sse_transport = SseServerTransport("/messages/")


async def handle_sse(request: Request) -> None:
    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        await server.run(
            streams[0], streams[1], server.create_initialization_options()
        )


starlette_app = Starlette(
    routes=[
        Route("/sse", endpoint=handle_sse),
        Mount("/messages/", app=sse_transport.handle_post_message),
    ]
)


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("LOCAL_SCALE_MCP_PORT", "8001"))
    host = os.getenv("LOCAL_SCALE_MCP_HOST", "0.0.0.0")
    print(f"🏥  Apple Health MCP server starting")
    print(f"    SSE stream : http://{host}:{port}/sse")
    print(f"    Messages   : http://{host}:{port}/messages/")
    print(f"    Database   : {_settings.database_url}")
    print(f"    Tools      : {len(TOOLS)}")
    uvicorn.run(starlette_app, host=host, port=port)
