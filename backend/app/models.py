from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    sex: Mapped[str] = mapped_column(String(16), nullable=False)
    birth_date: Mapped[date] = mapped_column(Date, nullable=False)
    height_cm: Mapped[float] = mapped_column(Float, nullable=False)
    units: Mapped[str] = mapped_column(String(8), default="metric", nullable=False)
    color: Mapped[str] = mapped_column(String(16), default="#0f766e", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )

    measurements: Mapped[list["Measurement"]] = relationship(back_populates="profile")


class ScaleDevice(Base):
    __tablename__ = "scale_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    address: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    advertised_name: Mapped[str] = mapped_column(String(120), nullable=False)
    model_family: Mapped[str | None] = mapped_column(String(120))
    protocol_family: Mapped[str | None] = mapped_column(String(120))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    profile_id: Mapped[int | None] = mapped_column(ForeignKey("profiles.id"))
    rows_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_imported: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Measurement(Base):
    __tablename__ = "measurements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    assignment_state: Mapped[str] = mapped_column(String(32), nullable=False, default="confirmed")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    anomaly_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    note: Mapped[str | None] = mapped_column(Text)

    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    waist_cm: Mapped[float | None] = mapped_column(Float)
    triglycerides_mmol_l: Mapped[float | None] = mapped_column(Float)
    hdl_mmol_l: Mapped[float | None] = mapped_column(Float)
    bmi: Mapped[float | None] = mapped_column(Float)
    fat_pct: Mapped[float | None] = mapped_column(Float)
    fat_weight_kg: Mapped[float | None] = mapped_column(Float)
    skeletal_muscle_pct: Mapped[float | None] = mapped_column(Float)
    skeletal_muscle_weight_kg: Mapped[float | None] = mapped_column(Float)
    muscle_pct: Mapped[float | None] = mapped_column(Float)
    muscle_weight_kg: Mapped[float | None] = mapped_column(Float)
    visceral_fat: Mapped[float | None] = mapped_column(Float)
    visceral_adiposity_index: Mapped[float | None] = mapped_column(Float)
    water_pct: Mapped[float | None] = mapped_column(Float)
    water_weight_kg: Mapped[float | None] = mapped_column(Float)
    bone_weight_kg: Mapped[float | None] = mapped_column(Float)
    bmr_kcal: Mapped[float | None] = mapped_column(Float)
    metabolic_age: Mapped[int | None] = mapped_column(Integer)
    body_age: Mapped[int | None] = mapped_column(Integer)
    status_by_metric: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    source_metric_map: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    raw_payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    profile: Mapped[Profile] = relationship(back_populates="measurements")


class WeighSession(Base):
    __tablename__ = "weigh_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    selected_profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    adapter_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    measurement_id: Mapped[int | None] = mapped_column(ForeignKey("measurements.id"))
    anomaly_score: Mapped[float | None] = mapped_column(Float)
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
