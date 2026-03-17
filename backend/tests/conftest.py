from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    repo_root = Path(__file__).resolve().parents[2]
    return Settings(
        app_name="Local Scale Test",
        env="test",
        api_prefix="/api",
        database_url=f"sqlite:///{tmp_path / 'test.sqlite3'}",
        adapter_mode="replay",
        replay_fixture_path=repo_root / "fixtures" / "replay" / "sample_measurements.json",
        import_fixture_path=repo_root / "fixtures" / "imports" / "sample_import.csv",
        frontend_dist_path=repo_root / "frontend" / "dist",
        cors_origins=("http://localhost:5173",),
        session_timeout_seconds=10,
        replay_delay_seconds=0.01,
        seed_demo_data=True,
        target_scale_names=("Soundlogic", "OKOK", "Chipsea"),
    )


@pytest.fixture()
def client(settings: Settings) -> TestClient:
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
