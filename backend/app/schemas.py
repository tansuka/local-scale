from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field
from pydantic.functional_serializers import field_serializer

from app.core.config import get_settings


def _get_display_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().display_timezone)


def _serialize_datetime_local(value: datetime) -> str:
    """Serialize a datetime in the configured display timezone (e.g. Europe/Amsterdam).

    DB stores UTC; this converts on output so agents and frontends see local time.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(_get_display_tz()).isoformat()



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
    waist_cm: float | None = None
    triglycerides_mmol_l: float | None = None
    hdl_mmol_l: float | None = None
    bmi: float | None = None
    fat_pct: float | None = None
    fat_weight_kg: float | None = None
    skeletal_muscle_pct: float | None = None
    skeletal_muscle_weight_kg: float | None = None
    muscle_pct: float | None = None
    muscle_weight_kg: float | None = None
    visceral_fat: float | None = None
    visceral_adiposity_index: float | None = None
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
        return _serialize_datetime_local(value)


class MeasurementReassignRequest(BaseModel):
    profile_id: int


class MeasurementUpdateRequest(BaseModel):
    waist_cm: float | None = Field(default=None, gt=0)
    triglycerides_mmol_l: float | None = Field(default=None, gt=0)
    hdl_mmol_l: float | None = Field(default=None, gt=0)


class MeasurementSubmitRequest(BaseModel):
    profile_id: int
    measured_at: datetime
    source: str = "ios_bluetooth"
    weight_kg: float = Field(gt=0)
    raw_payload_json: dict[str, Any] = Field(default_factory=dict)
    source_metric_map: dict[str, str] = Field(default_factory=dict)


class HealthAnalysisRunRequest(BaseModel):
    """Optional request body for POST /admin/profiles/{id}/health-analysis/run.
    Contains ephemeral Apple Health context to enrich the LLM prompt."""
    apple_health: dict[str, Any] | None = None


class ChartPoint(BaseModel):
    measured_at: datetime
    value: float

    @field_serializer("measured_at")
    def serialize_measured_at(self, value: datetime) -> str:
        return _serialize_datetime_local(value)


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
        return _serialize_datetime_local(value)


class ImportPreviewRow(BaseModel):
    row_number: int
    measured_at: datetime | None
    profile_name: str | None
    weight_kg: float | None
    waist_cm: float | None = None
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
    health_analysis: "HealthAnalysisRead | None" = None


class HealthAnalysisRead(BaseModel):
    status: str
    summary: str | None = None
    concern_level: str | None = None
    highlights: list[str] = Field(default_factory=list)
    advice: str | None = None
    generated_at: datetime | None = None
    measurement_count: int = 0
    is_stale: bool = False
    error_message: str | None = None

    @field_serializer("generated_at", when_used="json-unless-none")
    def serialize_generated_at(self, value: datetime) -> str:
        return _serialize_datetime_local(value)


class LlmSettingsRead(BaseModel):
    base_url: str
    model: str
    has_api_key: bool
    api_key_preview: str | None = None
    prompt_path: str
    prompt_loaded: bool
    prompt_error: str | None = None


class LlmSettingsUpdateRequest(BaseModel):
    base_url: str = ""
    model: str = ""
    api_key: str | None = None
    clear_api_key: bool = False


class AppleHealthSyncRequest(BaseModel):
    profile_id: int
    snapshot: dict[str, Any]  # Full AppleHealthSnapshot JSON — flexible schema
