from __future__ import annotations

from pathlib import Path
import threading

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_events, get_health_analyzer, get_session_manager
from app.db import Database
from app.models import Measurement
from app.repositories.measurements import (
    chart_series,
    delete_measurement,
    list_measurements,
    reassign_measurement,
    update_measurement,
)
from app.repositories.profiles import create_profile, get_profile, list_profiles, update_profile
from app.schemas import (
    ChartPoint,
    ChartResponse,
    DashboardPayload,
    HealthAnalysisRead,
    ImportCommitResponse,
    ImportPreviewResponse,
    LlmSettingsRead,
    LlmSettingsUpdateRequest,
    MeasurementRead,
    MeasurementReassignRequest,
    MeasurementUpdateRequest,
    ProfileCreate,
    ProfileRead,
    StartSessionRequest,
    WeighSessionRead,
)
from app.services.events import EventBroker
from app.services.imports import commit_csv_upload, preview_csv_upload
from app.services.llm_health import LlmHealthAnalyzer
from app.services.metrics import measurement_to_chart_value, normalize_measurement
from app.services.sessions import SessionManager

router = APIRouter()


def _refresh_health_analysis_in_background(
    database: Database,
    analyzer: LlmHealthAnalyzer,
    profile_id: int,
) -> None:
    try:
        with database.make_session() as db:
            profile = get_profile(db, profile_id)
            if profile is None:
                return
            analyzer.resolve_analysis(db, profile, force_refresh=True)
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
                threading.Thread(
                    target=_refresh_health_analysis_in_background,
                    args=(database, health_analyzer, profile.id),
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


@router.post("/admin/profiles/{profile_id}/health-analysis/run", response_model=HealthAnalysisRead)
def post_run_profile_health_analysis(
    profile_id: int,
    db: Session = Depends(get_db),
    health_analyzer: LlmHealthAnalyzer = Depends(get_health_analyzer),
) -> HealthAnalysisRead:
    profile = get_profile(db, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return health_analyzer.resolve_analysis(db, profile, force_refresh=True)


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
