from __future__ import annotations

import asyncio
from pathlib import Path
import threading

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_events, get_health_analyzer, get_session_manager
from app.db import Database
from app.models import Measurement
from app.repositories.apple_health import get_latest_snapshot as get_latest_apple_health_snapshot, list_snapshot_metadata
from app.repositories.measurements import (
    add_measurement,
    chart_series,
    delete_measurement,
    is_duplicate,
    list_measurements,
    reassign_measurement,
    recent_measurements,
    update_measurement,
)
from app.repositories.profiles import create_profile, get_profile, list_profiles, update_profile
from app.schemas import (
    AppleHealthSyncRequest,
    ChartPoint,
    ChartResponse,
    DashboardPayload,
    HealthAnalysisRead,
    HealthAnalysisRunRequest,
    ImportCommitResponse,
    ImportPreviewResponse,
    LlmSettingsRead,
    LlmSettingsUpdateRequest,
    MeasurementRead,
    MeasurementReassignRequest,
    MeasurementSubmitRequest,
    MeasurementUpdateRequest,
    ProfileCreate,
    ProfileRead,
    StartSessionRequest,
    WeighSessionRead,
)
from app.services.events import EventBroker
from app.services.imports import commit_csv_upload, preview_csv_upload
from app.services.llm_health import LlmHealthAnalyzer
from app.services.anomaly import anomaly_score, requires_confirmation
from app.services.metrics import measurement_to_chart_value, normalize_measurement
from app.services.sessions import SessionManager

router = APIRouter()


def _refresh_health_analysis_in_background(
    database: Database,
    analyzer: LlmHealthAnalyzer,
    profile_id: int,
    events: EventBroker,
    apple_health: dict | None = None,
) -> None:
    try:
        with database.make_session() as db:
            profile = get_profile(db, profile_id)
            if profile is None:
                return
            analysis = analyzer.resolve_analysis(
                db, profile, force_refresh=True, apple_health=apple_health,
            )
            try:
                asyncio.run(
                    events.broadcast(
                        {
                            "type": "health_analysis.updated",
                            "profile_id": profile_id,
                            "health_analysis": analysis.model_dump(mode="json"),
                        }
                    )
                )
            except Exception:
                pass  # Best-effort: analysis is saved even if broadcast fails
    finally:
        analyzer.mark_refresh_finished(profile_id)


def _measurement_normalize_payload(measurement: Measurement, *, source_metric_map: dict[str, str]) -> dict:
    return {
        "measured_at": measurement.measured_at,
        "source": measurement.source,
        "weight_kg": measurement.weight_kg,
        "waist_cm": measurement.waist_cm,
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
    }


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/profiles", response_model=list[ProfileRead])
def get_profiles(db: Session = Depends(get_db)) -> list[ProfileRead]:
    return [ProfileRead.model_validate(item) for item in list_profiles(db)]


@router.post("/profiles", response_model=ProfileRead, status_code=201)
def post_profile(
    payload: ProfileCreate,
    db: Session = Depends(get_db),
) -> ProfileRead:
    return ProfileRead.model_validate(create_profile(db, payload))


@router.put("/profiles/{profile_id}", response_model=ProfileRead)
def put_profile(
    profile_id: int,
    payload: ProfileCreate,
    db: Session = Depends(get_db),
) -> ProfileRead:
    profile = get_profile(db, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return ProfileRead.model_validate(update_profile(db, profile, payload))


@router.get("/measurements", response_model=list[MeasurementRead])
def get_measurements(
    profile_id: int | None = Query(default=None),
    limit: int = Query(default=100, le=365),
    db: Session = Depends(get_db),
) -> list[MeasurementRead]:
    return [
        MeasurementRead.model_validate(item)
        for item in list_measurements(db, profile_id=profile_id, limit=limit)
    ]


@router.post("/measurements/{measurement_id}/reassign-profile", response_model=MeasurementRead)
def post_reassign_measurement(
    measurement_id: int,
    payload: MeasurementReassignRequest,
    db: Session = Depends(get_db),
) -> MeasurementRead:
    measurement = reassign_measurement(db, measurement_id, payload.profile_id)
    if measurement is None:
        raise HTTPException(status_code=404, detail="Measurement not found")
    return MeasurementRead.model_validate(measurement)


@router.patch("/measurements/{measurement_id}", response_model=MeasurementRead)
def patch_measurement(
    measurement_id: int,
    payload: MeasurementUpdateRequest,
    db: Session = Depends(get_db),
) -> MeasurementRead:
    measurement = db.get(Measurement, measurement_id)
    if measurement is None:
        raise HTTPException(status_code=404, detail="Measurement not found")

    update_payload = {
        key: getattr(payload, key)
        for key in ("waist_cm", "triglycerides_mmol_l", "hdl_mmol_l")
        if key in payload.model_fields_set
    }
    if not update_payload:
        return MeasurementRead.model_validate(measurement)

    profile = get_profile(db, measurement.profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    source_metric_map = dict(measurement.source_metric_map or {})
    for key, value in update_payload.items():
        if value is None:
            source_metric_map.pop(key, None)
        else:
            source_metric_map[key] = "manual_edit"
    source_metric_map.pop("visceral_adiposity_index", None)

    normalized = normalize_measurement(
        profile,
        {
            **_measurement_normalize_payload(
                measurement,
                source_metric_map=source_metric_map,
            ),
            **update_payload,
            "visceral_adiposity_index": None,
        },
    )
    measurement = update_measurement(db, measurement_id, normalized)
    return MeasurementRead.model_validate(measurement)


@router.delete("/measurements/{measurement_id}", status_code=204, response_model=None)
def delete_measurement_route(
    measurement_id: int,
    db: Session = Depends(get_db),
):
    deleted = delete_measurement(db, measurement_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Measurement not found")


@router.post("/measurements/submit", response_model=MeasurementRead, status_code=201)
async def post_submit_measurement(
    payload: MeasurementSubmitRequest,
    db: Session = Depends(get_db),
    events: EventBroker = Depends(get_events),
) -> MeasurementRead:
    # 1. Validate profile
    profile = get_profile(db, payload.profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    # 2. Check duplicate (same weight ±0.05kg within ±2 min window)
    if is_duplicate(
        db,
        profile_id=profile.id,
        measured_at=payload.measured_at,
        weight_kg=payload.weight_kg,
    ):
        raise HTTPException(status_code=409, detail="Duplicate measurement")
    # 3. Build raw dict and normalize (computes BMI, fat%, muscle%, etc.)
    raw = {
        "measured_at": payload.measured_at,
        "source": payload.source,
        "weight_kg": payload.weight_kg,
        "raw_payload_json": payload.raw_payload_json,
        "source_metric_map": payload.source_metric_map,
    }
    # Carry forward waist_cm from most recent measurement if available
    recent = recent_measurements(db, profile.id, limit=14)
    latest_waist = next(
        (m.waist_cm for m in recent if m.waist_cm is not None), None
    )
    if latest_waist is not None:
        raw["waist_cm"] = latest_waist
        raw["source_metric_map"] = {
            **raw["source_metric_map"],
            "waist_cm": "carried_forward",
        }
    normalized = normalize_measurement(profile, raw)
    # 4. Anomaly scoring
    score = anomaly_score(recent, normalized)
    needs_confirmation = requires_confirmation(score, normalized, recent)
    # 5. Persist
    stored = add_measurement(
        db,
        {
            **normalized,
            "profile_id": profile.id,
            "assignment_state": "pending_confirmation" if needs_confirmation else "confirmed",
            "confidence": round(max(0.05, 1.0 - score), 3),
            "anomaly_score": score,
            "note": (
                "Needs confirmation — unusual reading for this profile."
                if needs_confirmation
                else "Saved from iOS."
            ),
        },
    )
    # 6. Broadcast to WebSocket clients
    await events.broadcast(
        {
            "type": "measurement.created",
            "measurement": MeasurementRead.model_validate(stored).model_dump(mode="json"),
        }
    )
    return MeasurementRead.model_validate(stored)


def _build_chart_response(profile_id: int, rows: list[Measurement]) -> ChartResponse:
    metrics = [
        "weight_kg",
        "waist_cm",
        "bmi",
        "fat_pct",
        "skeletal_muscle_weight_kg",
        "skeletal_muscle_pct",
        "water_pct",
        "visceral_adiposity_index",
        "visceral_fat",
        "bmr_kcal",
    ]
    series: dict[str, list[ChartPoint]] = {}
    for metric in metrics:
        points = []
        for row in rows:
            value = measurement_to_chart_value(row, metric)
            if value is not None:
                points.append(ChartPoint(measured_at=row.measured_at, value=float(value)))
        series[metric] = points
    return ChartResponse(profile_id=profile_id, series=series)


@router.get("/charts/{profile_id}", response_model=ChartResponse)
def get_charts(profile_id: int, db: Session = Depends(get_db)) -> ChartResponse:
    if get_profile(db, profile_id) is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    rows = chart_series(db, profile_id)["rows"]
    return _build_chart_response(profile_id, rows)


@router.get("/dashboard", response_model=DashboardPayload)
def get_dashboard(
    request: Request,
    profile_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    health_analyzer: LlmHealthAnalyzer = Depends(get_health_analyzer),
) -> DashboardPayload:
    profiles = list_profiles(db)
    selected_profile = profile_id or (profiles[0].id if profiles else None)
    measurements = list_measurements(db, profile_id=selected_profile, limit=365) if selected_profile else []
    charts = None
    health_analysis: HealthAnalysisRead | None = None
    if selected_profile is not None:
        charts = _build_chart_response(selected_profile, chart_series(db, selected_profile)["rows"])
        profile = get_profile(db, selected_profile)
        if profile is not None:
            analysis_snapshot = health_analyzer.analysis_snapshot(db, profile)
            health_analysis = analysis_snapshot.analysis
            if analysis_snapshot.should_refresh and health_analyzer.mark_refresh_started(profile.id):
                database: Database = request.app.state.db
                events_broker: EventBroker = request.app.state.events
                threading.Thread(
                    target=_refresh_health_analysis_in_background,
                    args=(database, health_analyzer, profile.id, events_broker),
                    daemon=True,
                ).start()
    return DashboardPayload(
        profiles=[ProfileRead.model_validate(item) for item in profiles],
        selected_profile_id=selected_profile,
        measurements=[MeasurementRead.model_validate(item) for item in measurements],
        charts=charts,
        health_analysis=health_analysis,
    )


@router.get("/admin/llm-settings", response_model=LlmSettingsRead)
def get_admin_llm_settings(
    db: Session = Depends(get_db),
    health_analyzer: LlmHealthAnalyzer = Depends(get_health_analyzer),
) -> LlmSettingsRead:
    return health_analyzer.get_settings_view(db)


@router.put("/admin/llm-settings", response_model=LlmSettingsRead)
def put_admin_llm_settings(
    payload: LlmSettingsUpdateRequest,
    db: Session = Depends(get_db),
    health_analyzer: LlmHealthAnalyzer = Depends(get_health_analyzer),
) -> LlmSettingsRead:
    return health_analyzer.save_settings(db, payload)


@router.post("/admin/profiles/{profile_id}/health-analysis/run", response_model=HealthAnalysisRead, status_code=202)
def post_run_profile_health_analysis(
    profile_id: int,
    request: Request,
    payload: HealthAnalysisRunRequest | None = None,
    db: Session = Depends(get_db),
    health_analyzer: LlmHealthAnalyzer = Depends(get_health_analyzer),
) -> HealthAnalysisRead:
    profile = get_profile(db, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    apple_health = payload.apple_health if payload else None
    if health_analyzer.mark_refresh_started(profile_id):
        database: Database = request.app.state.db
        events_broker: EventBroker = request.app.state.events
        threading.Thread(
            target=_refresh_health_analysis_in_background,
            args=(database, health_analyzer, profile_id, events_broker),
            kwargs={"apple_health": apple_health},
            daemon=True,
        ).start()
    return HealthAnalysisRead(
        status="pending",
        measurement_count=0,
    )


@router.post("/sessions/start", response_model=WeighSessionRead, status_code=202)
async def post_start_session(
    payload: StartSessionRequest,
    db: Session = Depends(get_db),
    session_manager: SessionManager = Depends(get_session_manager),
) -> WeighSessionRead:
    if get_profile(db, payload.selected_profile_id) is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    session = await session_manager.start_session(db, payload.selected_profile_id)
    return WeighSessionRead.model_validate(session)


@router.get("/sessions/current", response_model=WeighSessionRead | None)
def get_current_session(
    db: Session = Depends(get_db),
    session_manager: SessionManager = Depends(get_session_manager),
) -> WeighSessionRead | None:
    session = session_manager.latest(db)
    if session is None:
        return None
    return WeighSessionRead.model_validate(session)


@router.post("/sessions/{session_id}/cancel", response_model=WeighSessionRead)
async def post_cancel_session(
    session_id: str,
    db: Session = Depends(get_db),
    session_manager: SessionManager = Depends(get_session_manager),
) -> WeighSessionRead:
    session = await session_manager.cancel_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return WeighSessionRead.model_validate(session)


@router.post("/imports/csv/preview", response_model=ImportPreviewResponse)
async def post_import_preview(file: UploadFile = File(...)) -> ImportPreviewResponse:
    return await preview_csv_upload(file)


@router.post("/imports/csv/commit", response_model=ImportCommitResponse)
async def post_import_commit(
    file: UploadFile = File(...),
    profile_id: int | None = Form(default=None),
    db: Session = Depends(get_db),
) -> ImportCommitResponse:
    batch, errors = await commit_csv_upload(db, file, profile_id=profile_id)
    return ImportCommitResponse(
        batch_id=batch.id,
        imported=batch.rows_imported,
        skipped=batch.rows_skipped,
        errors=errors,
    )


# ── Apple Health Full Sync ─────────────────────────────────────────


@router.post("/apple-health/sync", status_code=201)
def post_apple_health_sync(
    payload: AppleHealthSyncRequest,
    db: Session = Depends(get_db),
) -> dict:
    from datetime import datetime, timezone
    from app.models import AppleHealthSnapshot

    profile = get_profile(db, payload.profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    def _parse_dt(raw, fallback: datetime) -> datetime:
        if isinstance(raw, str):
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                return fallback
        return fallback

    now = datetime.now(timezone.utc)
    captured_at = _parse_dt(payload.snapshot.get("captured_at"), now)
    period_start = _parse_dt(payload.snapshot.get("period_start"), now)
    period_end = _parse_dt(payload.snapshot.get("period_end"), now)

    snapshot = AppleHealthSnapshot(
        profile_id=payload.profile_id,
        captured_at=captured_at,
        period_start=period_start,
        period_end=period_end,
        payload_json=payload.snapshot,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return {"status": "ok", "id": snapshot.id}


@router.get("/apple-health/snapshots")
def get_apple_health_snapshots(
    profile_id: int,
    limit: int = Query(default=30, le=365),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Return metadata + full payload for stored Apple Health snapshots."""
    from app.models import AppleHealthSnapshot

    rows = (
        db.query(AppleHealthSnapshot)
        .filter_by(profile_id=profile_id)
        .order_by(AppleHealthSnapshot.captured_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "captured_at": r.captured_at,
            "period_start": r.period_start,
            "period_end": r.period_end,
            "payload": r.payload_json,
        }
        for r in rows
    ]


@router.websocket("/ws/live")
async def websocket_live(
    websocket: WebSocket,
    events: EventBroker = Depends(get_events),
) -> None:
    await events.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        events.disconnect(websocket)


def frontend_file(dist_path: Path, request_path: str) -> FileResponse | None:
    if not dist_path.exists():
        return None
    candidate = dist_path / request_path
    if request_path and candidate.exists() and candidate.is_file():
        return FileResponse(candidate)
    index_file = dist_path / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return None
