from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str
    env: str
    api_prefix: str
    database_url: str
    data_root: Path
    adapter_mode: str
    replay_fixture_path: Path
    import_fixture_path: Path
    frontend_dist_path: Path
    cors_origins: tuple[str, ...]
    session_timeout_seconds: int
    replay_delay_seconds: float
    seed_demo_data: bool
    target_scale_names: tuple[str, ...]
    ble_capture_dir: Path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    repo_root = _repo_root()
    backend_root = repo_root / "backend"
    data_root = Path(os.getenv("LOCAL_SCALE_DATA_DIR", repo_root / "data"))
    data_root.mkdir(parents=True, exist_ok=True)

    env = os.getenv("LOCAL_SCALE_ENV", "dev")
    adapter_mode = os.getenv(
        "LOCAL_SCALE_ADAPTER_MODE",
        "live" if env == "target" else "replay",
    )
    database_url = os.getenv(
        "LOCAL_SCALE_DATABASE_URL",
        f"sqlite:///{data_root / 'local_scale.sqlite3'}",
    )
    dist_path = Path(
        os.getenv("LOCAL_SCALE_FRONTEND_DIST", repo_root / "frontend" / "dist")
    )

    raw_origins = os.getenv(
        "LOCAL_SCALE_CORS_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173",
    )
    origins = tuple(origin.strip() for origin in raw_origins.split(",") if origin.strip())

    target_names = os.getenv(
        "LOCAL_SCALE_TARGET_NAMES",
        "Soundlogic,OKOK,Chipsea,BodyFatScale",
    )

    return Settings(
        app_name="Local Scale",
        env=env,
        api_prefix="/api",
        database_url=database_url,
        data_root=data_root,
        adapter_mode=adapter_mode,
        replay_fixture_path=Path(
            os.getenv(
                "LOCAL_SCALE_REPLAY_FIXTURE",
                repo_root / "fixtures" / "replay" / "sample_measurements.json",
            )
        ),
        import_fixture_path=Path(
            os.getenv(
                "LOCAL_SCALE_IMPORT_FIXTURE",
                repo_root / "fixtures" / "imports" / "sample_import.csv",
            )
        ),
        frontend_dist_path=dist_path,
        cors_origins=origins,
        session_timeout_seconds=int(
            os.getenv("LOCAL_SCALE_SESSION_TIMEOUT_SECONDS", "60")
        ),
        replay_delay_seconds=float(
            os.getenv("LOCAL_SCALE_REPLAY_DELAY_SECONDS", "1.75")
        ),
        seed_demo_data=env != "target"
        and os.getenv("LOCAL_SCALE_SEED_DEMO_DATA", "1") != "0",
        target_scale_names=tuple(
            part.strip() for part in target_names.split(",") if part.strip()
        ),
        ble_capture_dir=Path(
            os.getenv("LOCAL_SCALE_BLE_CAPTURE_DIR", data_root / "ble-captures")
        ),
    )
