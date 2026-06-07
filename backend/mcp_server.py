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



def _sample_value(samples: dict, hk_key: str) -> float | None:
    """Extract the numeric value from a latest_samples entry."""
    entry = samples.get(hk_key)
    if entry and isinstance(entry, dict):
        val = entry.get("value")
        return float(val) if val is not None else None
    return None


def _sample_date(samples: dict, hk_key: str) -> str | None:
    """Extract the actual measurement date from a latest_samples entry.

    Apple Health entries may have 'date', 'start_date', or 'end_date'.
    'date' or 'start_date' represents when the measurement was actually taken,
    which is distinct from the snapshot's 'captured_at' (the sync timestamp).
    """
    entry = samples.get(hk_key)
    if entry and isinstance(entry, dict):
        return entry.get("date") or entry.get("start_date") or None
    return None


def _sample_with_date(samples: dict, hk_key: str) -> dict | None:
    """Return {value, measured_at} for a latest_samples entry, or None if absent."""
    val = _sample_value(samples, hk_key)
    if val is None:
        return None
    dt = _sample_date(samples, hk_key)
    result: dict = {"value": val}
    if dt:
        result["measured_at"] = dt
    return result


def _avg_daily(daily_summaries: list[dict], hk_key: str) -> float | None:
    """Average a metric across all days in daily_summaries."""
    values: list[float] = []
    for d in daily_summaries:
        raw = d.get("metrics", {}).get(hk_key)
        if raw is None:
            continue
        try:
            values.append(float(raw))
        except (ValueError, TypeError):
            continue
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _compact(obj: Any) -> Any:
    """Recursively strip None values and empty dicts/lists to minimize tokens."""
    if isinstance(obj, dict):
        return {k: _compact(v) for k, v in obj.items() if v is not None and v != {} and v != []}
    if isinstance(obj, list):
        return [_compact(item) for item in obj]
    return obj


def _ok(data: dict) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=json.dumps(_compact(data), default=str, separators=(',', ':')))]


def _no_snapshot(profile_id: int) -> list[types.TextContent]:
    return _ok({"error": f"No Apple Health snapshot found for profile_id={profile_id}."})


def _snapshot_meta(snapshot: Any) -> dict:
    return {
        "profile_id": snapshot.profile_id,
        "synced_at": snapshot.captured_at.isoformat(),
        "period": f"{snapshot.period_start.isoformat()}/{snapshot.period_end.isoformat()}",
    }


# ── Category extractors ────────────────────────────────────────────────────────

def _extract_activity(payload: dict) -> dict:
    daily = payload.get("daily_summaries", [])
    return {
        "steps": _avg_daily(daily, "HKQuantityTypeIdentifierStepCount"),
        "active_energy_kcal": _avg_daily(daily, "HKQuantityTypeIdentifierActiveEnergyBurned"),
        "basal_energy_kcal": _avg_daily(daily, "HKQuantityTypeIdentifierBasalEnergyBurned"),
        "exercise_min": _avg_daily(daily, "HKQuantityTypeIdentifierAppleExerciseTime"),
        "walk_run_m": _avg_daily(daily, "HKQuantityTypeIdentifierDistanceWalkingRunning"),
        "cycling_m": _avg_daily(daily, "HKQuantityTypeIdentifierDistanceCycling"),
        "swimming_m": _avg_daily(daily, "HKQuantityTypeIdentifierDistanceSwimming"),
        "flights": _avg_daily(daily, "HKQuantityTypeIdentifierFlightsClimbed"),
        "stand_min": _avg_daily(daily, "HKQuantityTypeIdentifierAppleStandTime"),
        "move_min": _avg_daily(daily, "HKQuantityTypeIdentifierAppleMoveTime"),
        "daylight_min": _avg_daily(daily, "HKQuantityTypeIdentifierTimeInDaylight"),
    }


def _extract_heart(payload: dict) -> dict:
    samples = payload.get("latest_samples", {})

    # O2 saturation is stored as a ratio (0.98), convert to percentage
    o2_entry = _sample_with_date(samples, "HKQuantityTypeIdentifierOxygenSaturation")
    if o2_entry is not None:
        o2_entry["value"] = round(o2_entry["value"] * 100, 1)

    # Latest ECG summary
    ecg_readings = payload.get("ecg_readings", [])
    latest_ecg: dict | None = None
    if ecg_readings:
        ecg = ecg_readings[-1]
        latest_ecg = {
            "classification": ecg.get("classification"),
            "avg_hr_bpm": ecg.get("average_heart_rate"),
            "measured_at": ecg.get("start_date") or ecg.get("date"),
        }

    return {
        "resting_hr": _sample_with_date(samples, "HKQuantityTypeIdentifierRestingHeartRate"),
        "hrv_sdnn": _sample_with_date(samples, "HKQuantityTypeIdentifierHeartRateVariabilitySDNN"),
        "walking_hr_avg": _sample_with_date(samples, "HKQuantityTypeIdentifierWalkingHeartRateAverage"),
        "hr_recovery_1min": _sample_with_date(samples, "HKQuantityTypeIdentifierHeartRateRecoveryOneMinute"),
        "vo2_max": _sample_with_date(samples, "HKQuantityTypeIdentifierVo2Max"),
        "oxygen_saturation_pct": o2_entry,
        "blood_pressure_systolic": _sample_with_date(samples, "HKQuantityTypeIdentifierBloodPressureSystolic"),
        "blood_pressure_diastolic": _sample_with_date(samples, "HKQuantityTypeIdentifierBloodPressureDiastolic"),
        "afib_burden_pct": _sample_with_date(samples, "HKQuantityTypeIdentifierAtrialFibrillationBurden"),
        "latest_ecg": latest_ecg,
    }


def _extract_sleep(payload: dict) -> dict | None:
    """
    Extracts sleep data from recent_events.HKCategoryTypeIdentifierSleepAnalysis.
    Returns None if sleep data is not present in the snapshot.
    """
    events = payload.get("recent_events", {})
    sleep_events = events.get("HKCategoryTypeIdentifierSleepAnalysis", [])
    if not sleep_events:
        return None

    asleep_stages = {"asleep", "asleepCore", "asleepDeep", "asleepREM"}
    stage_minutes: dict[str, float] = {}
    total_asleep_min = 0.0

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
        stage_minutes[desc] = round(stage_minutes.get(desc, 0) + duration_min, 1)
        if desc in asleep_stages:
            total_asleep_min += duration_min

    total_hours = round(total_asleep_min / 60, 2)
    return {
        "total_hours": total_hours,
        "below_7h": total_hours < 7.0,
        "stages_min": stage_minutes,
    }


def _extract_nutrition(payload: dict) -> dict:
    daily = payload.get("daily_summaries", [])
    return {
        "calories_kcal": _avg_daily(daily, "HKQuantityTypeIdentifierDietaryEnergyConsumed"),
        "water_L": _avg_daily(daily, "HKQuantityTypeIdentifierDietaryWater"),
        "protein_g": _avg_daily(daily, "HKQuantityTypeIdentifierDietaryProtein"),
        "carbs_g": _avg_daily(daily, "HKQuantityTypeIdentifierDietaryCarbohydrates"),
        "fat_g": _avg_daily(daily, "HKQuantityTypeIdentifierDietaryFatTotal"),
        "sat_fat_g": _avg_daily(daily, "HKQuantityTypeIdentifierDietaryFatSaturated"),
        "fiber_g": _avg_daily(daily, "HKQuantityTypeIdentifierDietaryFiber"),
        "sugar_g": _avg_daily(daily, "HKQuantityTypeIdentifierDietarySugar"),
        "sodium_g": _avg_daily(daily, "HKQuantityTypeIdentifierDietarySodium"),
        "caffeine_g": _avg_daily(daily, "HKQuantityTypeIdentifierDietaryCaffeine"),
        "alcohol_drinks": _avg_daily(daily, "HKQuantityTypeIdentifierNumberOfAlcoholicBeverages"),
        "cholesterol_g": _avg_daily(daily, "HKQuantityTypeIdentifierDietaryCholesterol"),
    }


def _extract_vitals(payload: dict) -> dict:
    samples = payload.get("latest_samples", {})
    return {
        "body_temp_c": _sample_with_date(samples, "HKQuantityTypeIdentifierBodyTemperature"),
        "wrist_temp_c": _sample_with_date(samples, "HKQuantityTypeIdentifierAppleSleepingWristTemperature"),
        "basal_body_temp_c": _sample_with_date(samples, "HKQuantityTypeIdentifierBasalBodyTemperature"),
        "respiratory_rate": _sample_with_date(samples, "HKQuantityTypeIdentifierRespiratoryRate"),
        "blood_glucose": _sample_with_date(samples, "HKQuantityTypeIdentifierBloodGlucose"),
        "blood_alcohol_pct": _sample_with_date(samples, "HKQuantityTypeIdentifierBloodAlcoholContent"),
    }


def _extract_body_metrics(payload: dict) -> dict:
    samples = payload.get("latest_samples", {})
    # Body fat is stored as a ratio (0.165 = 16.5%) — convert to percentage
    fat_entry = _sample_with_date(samples, "HKQuantityTypeIdentifierBodyFatPercentage")
    if fat_entry is not None:
        fat_entry["value"] = round(fat_entry["value"] * 100, 1)
    return {
        "weight_kg": _sample_with_date(samples, "HKQuantityTypeIdentifierBodyMass"),
        "body_fat_pct": fat_entry,
        "bmi": _sample_with_date(samples, "HKQuantityTypeIdentifierBodyMassIndex"),
        "lean_mass_kg": _sample_with_date(samples, "HKQuantityTypeIdentifierLeanBodyMass"),
        "waist_cm": _sample_with_date(samples, "HKQuantityTypeIdentifierWaistCircumference"),
        "height_m": _sample_with_date(samples, "HKQuantityTypeIdentifierHeight"),
    }


def _extract_workouts(payload: dict) -> list[dict]:
    return [
        {
            "type": w.get("type"),
            "start": w.get("start_date"),
            "dur_min": w.get("duration_minutes"),
            "kcal": w.get("energy_burned_kcal"),
            "dist_m": w.get("distance_meters"),
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
            "Full Apple Health overview: activity, heart, sleep, nutrition, vitals, body metrics, workouts, symptoms. "
            "'synced_at' = when data was sent from iPhone. Each metric has its own 'measured_at' = actual reading time. "
            "Null metrics are omitted. Daily metrics are period averages."
        ),
        inputSchema=_PROFILE_ID_SCHEMA,
    ),
    types.Tool(
        name="get_activity",
        description="Daily activity averages: steps, energy, exercise, distance, flights, stand/move time, daylight.",
        inputSchema=_PROFILE_ID_SCHEMA,
    ),
    types.Tool(
        name="get_heart",
        description="Heart: resting HR, HRV, walking HR, recovery, VO2max, O2 sat, BP, AFib, ECG. Each has measured_at.",
        inputSchema=_PROFILE_ID_SCHEMA,
    ),
    types.Tool(
        name="get_sleep",
        description="Sleep: total hours, below-7h flag, minutes per stage (core/deep/REM/awake/inBed).",
        inputSchema=_PROFILE_ID_SCHEMA,
    ),
    types.Tool(
        name="get_nutrition",
        description="Nutrition averages: calories, water, protein, carbs, fat, fiber, sugar, sodium, caffeine, alcohol.",
        inputSchema=_PROFILE_ID_SCHEMA,
    ),
    types.Tool(
        name="get_vitals",
        description="Vitals: body/wrist temp, respiratory rate, blood glucose, blood alcohol. Each has measured_at.",
        inputSchema=_PROFILE_ID_SCHEMA,
    ),
    types.Tool(
        name="get_body_metrics",
        description="Body: weight, fat%, BMI, lean mass, waist, height from Apple Health (not scale BIA). Each has measured_at.",
        inputSchema=_PROFILE_ID_SCHEMA,
    ),
    types.Tool(
        name="get_workouts",
        description="Workout sessions: type, start, duration, calories, distance.",
        inputSchema=_PROFILE_ID_SCHEMA,
    ),
    types.Tool(
        name="get_symptoms",
        description="Active symptoms with severity and time window. Empty if none.",
        inputSchema=_PROFILE_ID_SCHEMA,
    ),
    types.Tool(
        name="get_snapshots_list",
        description="List available snapshots (id, synced_at, period). Check freshness before heavier calls.",
        inputSchema={
            "type": "object",
            "properties": {
                "profile_id": {
                    "type": "integer",
                    "description": "Profile ID.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max snapshots (default 10, max 90).",
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
        return _ok({"profile_id": profile_id, "snapshots": rows})

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
                "sleep": sleep or "no_data",
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
                "sleep": sleep or "no_data",
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
