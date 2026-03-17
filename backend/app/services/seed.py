from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Measurement, Profile
from app.services.metrics import normalize_measurement


def seed_demo_data(db: Session, fixture_path: str) -> None:
    if db.scalar(select(Profile.id).limit(1)) is not None:
        return

    payload = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
    for profile_payload in payload.get("profiles", []):
        profile = Profile(
            name=profile_payload["name"],
            sex=profile_payload["sex"],
            birth_date=date.fromisoformat(profile_payload["birth_date"]),
            height_cm=profile_payload["height_cm"],
            units=profile_payload.get("units", "metric"),
            color=profile_payload.get("color", "#0f766e"),
            notes=profile_payload.get("notes"),
        )
        db.add(profile)
        db.flush()

        for measurement_payload in profile_payload.get("measurements", []):
            normalized = normalize_measurement(
                profile,
                {
                    **measurement_payload,
                    "measured_at": datetime.fromisoformat(measurement_payload["measured_at"]),
                    "source": measurement_payload.get("source", "seed"),
                    "raw_payload_json": measurement_payload.get(
                        "raw_payload_json", {"seeded": True}
                    ),
                },
            )
            db.add(
                Measurement(
                    profile_id=profile.id,
                    assignment_state="confirmed",
                    confidence=1.0,
                    anomaly_score=0.0,
                    note="Seeded demo data",
                    **normalized,
                )
            )

    db.commit()
