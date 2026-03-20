from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.functional_serializers import field_serializer


def _serialize_datetime_assuming_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class ProfileCreate(BaseModel):
    name: str
    sex: str
    birth_date: date
    height_cm: float = Field(gt=0)
    units: str = "metric"
    color: str = "#0f766e"
    notes: str | None = None


class ProfileRead(ProfileCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    active: bool


class MeasurementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_id: int
    measured_at: datetime
    source: str
    assignment_state: str
    confidence: float
    anomaly_score: float
    note: str | None = None
    weight_kg: float
    bmi: float | None = None
    fat_pct: float | None = None
    fat_weight_kg: float | None = None
    skeletal_muscle_pct: float | None = None
    skeletal_muscle_weight_kg: float | None = None
    muscle_pct: float | None = None
    muscle_weight_kg: float | None = None
    visceral_fat: float | None = None
    water_pct: float | None = None
    water_weight_kg: float | None = None
    bone_weight_kg: float | None = None
    bmr_kcal: float | None = None
    metabolic_age: int | None = None
    body_age: int | None = None
    status_by_metric: dict[str, str]
    source_metric_map: dict[str, str]
    raw_payload_json: dict[str, Any]

    @field_serializer("measured_at")
    def serialize_measured_at(self, value: datetime) -> str:
        return _serialize_datetime_assuming_utc(value)


class MeasurementReassignRequest(BaseModel):
    profile_id: int


class ChartPoint(BaseModel):
    measured_at: datetime
    value: float

    @field_serializer("measured_at")
    def serialize_measured_at(self, value: datetime) -> str:
        return _serialize_datetime_assuming_utc(value)


class ChartResponse(BaseModel):
    profile_id: int
    series: dict[str, list[ChartPoint]]


class StartSessionRequest(BaseModel):
    selected_profile_id: int


class WeighSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    selected_profile_id: int
    status: str
    adapter_mode: str
    started_at: datetime
    expires_at: datetime
    completed_at: datetime | None = None
    measurement_id: int | None = None
    anomaly_score: float | None = None
    requires_confirmation: bool
    error_message: str | None = None

    @field_serializer("started_at", "expires_at", "completed_at", when_used="json-unless-none")
    def serialize_session_datetimes(self, value: datetime) -> str:
        return _serialize_datetime_assuming_utc(value)


class ImportPreviewRow(BaseModel):
    row_number: int
    measured_at: datetime | None
    profile_name: str | None
    weight_kg: float | None
    bmi: float | None = None
    fat_pct: float | None = None
    water_pct: float | None = None
    muscle_pct: float | None = None
    notes: list[str] = Field(default_factory=list)


class ImportPreviewResponse(BaseModel):
    source_name: str
    inferred_columns: dict[str, str]
    rows: list[ImportPreviewRow]
    warnings: list[str]


class ImportCommitResponse(BaseModel):
    batch_id: int
    imported: int
    skipped: int
    errors: list[dict[str, Any]]


class DashboardPayload(BaseModel):
    profiles: list[ProfileRead]
    selected_profile_id: int | None
    measurements: list[MeasurementRead]
    charts: ChartResponse | None = None
