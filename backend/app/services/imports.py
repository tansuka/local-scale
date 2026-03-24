from __future__ import annotations

import csv
from datetime import datetime, timezone
from io import StringIO
from typing import Any

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.models import ImportBatch
from app.repositories.measurements import add_measurement, is_duplicate, latest_known_measurement_value
from app.repositories.profiles import get_profile, get_profile_by_name
from app.schemas import ImportPreviewResponse, ImportPreviewRow
from app.services.metrics import normalize_measurement

FIELD_ALIASES = {
    "measured_at": {"measured_at", "timestamp", "date", "datetime", "recorded_at"},
    "profile_name": {"profile", "profile_name", "user", "name"},
    "weight_kg": {"weight", "weight_kg", "kg"},
    "waist_cm": {"waist", "waist_cm", "waist_circumference"},
    "triglycerides_mmol_l": {"triglycerides_mmol_l", "triglycerides", "tg_mmol_l", "tg"},
    "hdl_mmol_l": {"hdl_mmol_l", "hdl", "hdl_cholesterol"},
    "bmi": {"bmi"},
    "fat_pct": {"fat_pct", "fat", "body_fat", "body_fat_pct"},
    "water_pct": {"water_pct", "water"},
    "muscle_pct": {"muscle_pct", "muscle"},
    "skeletal_muscle_pct": {"skeletal_muscle_pct", "skeletal_muscle"},
    "visceral_fat": {"visceral_fat", "v_fat"},
}


def _infer_columns(headers: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    lowered = {header.lower(): header for header in headers}
    for canonical, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if alias in lowered:
                mapping[canonical] = lowered[alias]
                break
    return mapping


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


async def preview_csv_upload(upload: UploadFile) -> ImportPreviewResponse:
    raw = await upload.read()
    text = raw.decode("utf-8")
    reader = csv.DictReader(StringIO(text))
    headers = reader.fieldnames or []
    mapping = _infer_columns(headers)

    rows: list[ImportPreviewRow] = []
    warnings: list[str] = []
    if "weight_kg" not in mapping or "measured_at" not in mapping:
        warnings.append("Could not confidently map both timestamp and weight columns.")

    for index, row in enumerate(reader, start=1):
        notes: list[str] = []
        measured_at = _parse_datetime(row.get(mapping.get("measured_at", "")))
        if measured_at is None:
            notes.append("Missing or invalid timestamp")
        weight_kg = _parse_float(row.get(mapping.get("weight_kg", "")))
        if weight_kg is None:
            notes.append("Missing or invalid weight")
        rows.append(
            ImportPreviewRow(
                row_number=index,
                measured_at=measured_at,
                profile_name=row.get(mapping.get("profile_name", "")) or None,
                weight_kg=weight_kg,
                waist_cm=_parse_float(row.get(mapping.get("waist_cm", ""))),
                bmi=_parse_float(row.get(mapping.get("bmi", ""))),
                fat_pct=_parse_float(row.get(mapping.get("fat_pct", ""))),
                water_pct=_parse_float(row.get(mapping.get("water_pct", ""))),
                muscle_pct=_parse_float(row.get(mapping.get("muscle_pct", ""))),
                notes=notes,
            )
        )
        if index >= 12:
            break

    return ImportPreviewResponse(
        source_name=upload.filename or "import.csv",
        inferred_columns=mapping,
        rows=rows,
        warnings=warnings,
    )


async def commit_csv_upload(
    db: Session,
    upload: UploadFile,
    *,
    profile_id: int | None = None,
) -> tuple[ImportBatch, list[dict[str, Any]]]:
    raw = await upload.read()
    text = raw.decode("utf-8")
    reader = csv.DictReader(StringIO(text))
    headers = reader.fieldnames or []
    mapping = _infer_columns(headers)
    batch = ImportBatch(
        source_name=upload.filename or "import.csv",
        status="completed",
        profile_id=profile_id,
        rows_total=0,
        rows_imported=0,
        rows_skipped=0,
        errors_json=[],
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    errors: list[dict[str, Any]] = []
    for index, row in enumerate(reader, start=1):
        batch.rows_total += 1
        measured_at = _parse_datetime(row.get(mapping.get("measured_at", "")))
        weight_kg = _parse_float(row.get(mapping.get("weight_kg", "")))
        if measured_at is None or weight_kg is None:
            batch.rows_skipped += 1
            errors.append({"row": index, "error": "Missing timestamp or weight"})
            continue

        target_profile = None
        if profile_id is not None:
            target_profile = get_profile(db, profile_id)
        if target_profile is None:
            profile_name = row.get(mapping.get("profile_name", ""))
            if profile_name:
                target_profile = get_profile_by_name(db, profile_name)
        if target_profile is None:
            batch.rows_skipped += 1
            errors.append({"row": index, "error": "No target profile available"})
            continue

        if is_duplicate(
            db,
            profile_id=target_profile.id,
            measured_at=measured_at,
            weight_kg=weight_kg,
        ):
            batch.rows_skipped += 1
            errors.append({"row": index, "error": "Duplicate measurement"})
            continue

        imported_waist = _parse_float(row.get(mapping.get("waist_cm", "")))
        waist_source = "import"
        if imported_waist is None:
            imported_waist = latest_known_measurement_value(
                db,
                profile_id=target_profile.id,
                field_name="waist_cm",
                measured_at=measured_at,
            )
            if imported_waist is not None:
                waist_source = "carried_forward"

        payload = normalize_measurement(
            target_profile,
            {
                "measured_at": measured_at,
                "source": "import",
                "weight_kg": weight_kg,
                "waist_cm": imported_waist,
                "triglycerides_mmol_l": _parse_float(row.get(mapping.get("triglycerides_mmol_l", ""))),
                "hdl_mmol_l": _parse_float(row.get(mapping.get("hdl_mmol_l", ""))),
                "bmi": _parse_float(row.get(mapping.get("bmi", ""))),
                "fat_pct": _parse_float(row.get(mapping.get("fat_pct", ""))),
                "water_pct": _parse_float(row.get(mapping.get("water_pct", ""))),
                "muscle_pct": _parse_float(row.get(mapping.get("muscle_pct", ""))),
                "skeletal_muscle_pct": _parse_float(
                    row.get(mapping.get("skeletal_muscle_pct", ""))
                ),
                "visceral_fat": _parse_float(row.get(mapping.get("visceral_fat", ""))),
                "raw_payload_json": {"row": index, "source_name": batch.source_name},
                "source_metric_map": {
                    "weight_kg": "import",
                    "waist_cm": waist_source,
                    "triglycerides_mmol_l": "import",
                    "hdl_mmol_l": "import",
                    "fat_pct": "import",
                    "water_pct": "import",
                    "muscle_pct": "import",
                    "skeletal_muscle_pct": "import",
                    "visceral_fat": "import",
                },
            },
        )
        add_measurement(
            db,
            {
                **payload,
                "profile_id": target_profile.id,
                "assignment_state": "confirmed",
                "confidence": 1.0,
                "anomaly_score": 0.0,
                "note": "Imported from CSV",
            },
        )
        batch.rows_imported += 1

    batch.errors_json = errors
    db.commit()
    db.refresh(batch)
    return batch, errors
