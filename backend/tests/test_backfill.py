from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db import Database
from app.main import create_app
from app.models import Measurement, Profile
from app.services.anthropometric import backfill_missing_measurements


def _settings(tmp_path) -> Settings:
    repo_root = __import__("pathlib").Path(__file__).resolve().parents[2]
    return Settings(
        app_name="Local Scale Test",
        env="test",
        api_prefix="/api",
        database_url=f"sqlite:///{tmp_path / 'test.sqlite3'}",
        data_root=tmp_path,
        adapter_mode="replay",
        replay_fixture_path=repo_root / "fixtures" / "replay" / "sample_measurements.json",
        import_fixture_path=repo_root / "fixtures" / "imports" / "sample_import.csv",
        frontend_dist_path=repo_root / "frontend" / "dist",
        cors_origins=("http://localhost:5173",),
        session_timeout_seconds=10,
        replay_delay_seconds=0.01,
        ble_scan_timeout_seconds=1.0,
        ble_scan_rounds=1,
        ble_scan_pause_seconds=0.0,
        ble_connect_timeout_seconds=1.0,
        ble_connect_retries=1,
        ble_connect_retry_pause_seconds=0.0,
        ble_notify_capture_seconds=0.0,
        seed_demo_data=False,
        target_scale_names=("Soundlogic", "OKOK", "Chipsea"),
        target_scale_addresses=(),
        ble_capture_dir=tmp_path / "ble-captures",
    )


def _insert_incomplete_measurement(db):
    profile = Profile(
        name="Alex",
        sex="male",
        birth_date=date(1990, 1, 1),
        height_cm=180,
        units="metric",
        color="#0f766e",
        active=True,
    )
    db.add(profile)
    db.flush()
    measurement = Measurement(
        profile_id=profile.id,
        measured_at=datetime(2026, 3, 17, 7, 10, tzinfo=timezone.utc),
        source="import",
        assignment_state="confirmed",
        confidence=1.0,
        anomaly_score=0.0,
        note="Imported before fallback existed",
        weight_kg=74.19,
        bmi=22.9,
        fat_pct=None,
        fat_weight_kg=None,
        skeletal_muscle_pct=None,
        skeletal_muscle_weight_kg=None,
        muscle_pct=None,
        muscle_weight_kg=None,
        visceral_fat=None,
        water_pct=None,
        water_weight_kg=None,
        bone_weight_kg=None,
        bmr_kcal=None,
        metabolic_age=None,
        body_age=None,
        status_by_metric={},
        source_metric_map={"weight_kg": "import"},
        raw_payload_json={"row": 1},
    )
    db.add(measurement)
    db.commit()
    db.refresh(measurement)
    return measurement.id


def test_backfill_missing_measurements_updates_existing_rows(tmp_path):
    settings = _settings(tmp_path)
    database = Database(settings)
    database.create_all()

    with database.make_session() as db:
        measurement_id = _insert_incomplete_measurement(db)

    with database.make_session() as db:
        updated = backfill_missing_measurements(db)
        measurement = db.get(Measurement, measurement_id)

        assert updated == 1
        assert measurement is not None
        assert measurement.fat_pct == 19.56
        assert measurement.water_pct == 58.05
        assert measurement.fat_weight_kg == 14.51
        assert measurement.skeletal_muscle_weight_kg == 31.91
        assert measurement.water_weight_kg == 43.07
        assert measurement.source_metric_map["fat_pct"] == "anthropometric_estimated"
        assert measurement.source_metric_map["water_pct"] == "anthropometric_estimated"
        assert measurement.source_metric_map["skeletal_muscle_weight_kg"] == "anthropometric_estimated"


def test_app_startup_runs_backfill_for_existing_rows(tmp_path):
    settings = _settings(tmp_path)
    database = Database(settings)
    database.create_all()

    with database.make_session() as db:
        measurement_id = _insert_incomplete_measurement(db)

    app = create_app(settings)
    with TestClient(app):
        pass

    with database.make_session() as db:
        measurement = db.get(Measurement, measurement_id)

        assert measurement is not None
        assert measurement.fat_pct == 19.56
        assert measurement.water_pct == 58.05
        assert measurement.source_metric_map["fat_pct"] == "anthropometric_estimated"
        assert measurement.source_metric_map["water_pct"] == "anthropometric_estimated"
        assert measurement.source_metric_map["skeletal_muscle_weight_kg"] == "anthropometric_estimated"


def test_create_all_adds_waist_column_to_existing_profiles_table(tmp_path):
    settings = _settings(tmp_path)
    db_path = Path(settings.database_url.removeprefix("sqlite:///"))
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE profiles (
            id INTEGER PRIMARY KEY,
            name VARCHAR(120) NOT NULL UNIQUE,
            sex VARCHAR(16) NOT NULL,
            birth_date DATE NOT NULL,
            height_cm FLOAT NOT NULL,
            waist_cm FLOAT,
            units VARCHAR(8) NOT NULL,
            color VARCHAR(16) NOT NULL,
            active BOOLEAN NOT NULL,
            notes TEXT,
            created_at DATETIME,
            updated_at DATETIME
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE measurements (
            id INTEGER PRIMARY KEY,
            profile_id INTEGER NOT NULL,
            measured_at DATETIME NOT NULL,
            source VARCHAR(32) NOT NULL,
            assignment_state VARCHAR(32) NOT NULL,
            confidence FLOAT NOT NULL,
            anomaly_score FLOAT NOT NULL,
            note TEXT,
            weight_kg FLOAT NOT NULL,
            bmi FLOAT,
            fat_pct FLOAT,
            fat_weight_kg FLOAT,
            skeletal_muscle_pct FLOAT,
            skeletal_muscle_weight_kg FLOAT,
            muscle_pct FLOAT,
            muscle_weight_kg FLOAT,
            visceral_fat FLOAT,
            water_pct FLOAT,
            water_weight_kg FLOAT,
            bone_weight_kg FLOAT,
            bmr_kcal FLOAT,
            metabolic_age INTEGER,
            body_age INTEGER,
            status_by_metric JSON,
            source_metric_map JSON,
            raw_payload_json JSON
        )
        """
    )
    connection.execute(
        "INSERT INTO profiles (id, name, sex, birth_date, height_cm, waist_cm, units, color, active) VALUES (1, 'Alex', 'male', '1990-01-01', 180, 84, 'metric', '#0f766e', 1)"
    )
    connection.execute(
        "INSERT INTO measurements (id, profile_id, measured_at, source, assignment_state, confidence, anomaly_score, weight_kg, source_metric_map, raw_payload_json) VALUES (1, 1, '2026-03-17T07:10:00+00:00', 'import', 'confirmed', 1.0, 0.0, 74.19, '{}', '{}')"
    )
    connection.commit()
    connection.close()

    database = Database(settings)
    database.create_all()

    check_connection = sqlite3.connect(db_path)
    columns = {row[1] for row in check_connection.execute("PRAGMA table_info(measurements)").fetchall()}
    waist_value = check_connection.execute("SELECT waist_cm FROM measurements WHERE id = 1").fetchone()[0]
    check_connection.close()

    assert "waist_cm" in columns
    assert "triglycerides_mmol_l" in columns
    assert "hdl_mmol_l" in columns
    assert "visceral_adiposity_index" in columns
    assert waist_value == 84
