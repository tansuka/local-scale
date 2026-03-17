from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.api.routes import frontend_file, router
from app.core.config import Settings, get_settings
from app.db import Database
from app.services.adapters import build_scale_adapter
from app.services.events import EventBroker
from app.services.seed import seed_demo_data
from app.services.sessions import SessionManager


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    database = Database(settings)
    events = EventBroker()
    adapter = build_scale_adapter(settings)
    session_manager = SessionManager(
        database=database,
        adapter=adapter,
        events=events,
        adapter_mode=settings.adapter_mode,
        session_timeout_seconds=settings.session_timeout_seconds,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database.create_all()
        if settings.seed_demo_data:
            with database.make_session() as db:
                seed_demo_data(db, str(settings.replay_fixture_path))
        yield

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.settings = settings
    app.state.db = database
    app.state.events = events
    app.state.session_manager = session_manager

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router, prefix=settings.api_prefix)

    @app.get("/", response_model=None)
    def root():
        maybe_file = frontend_file(settings.frontend_dist_path, "")
        if maybe_file is not None:
            return maybe_file
        return JSONResponse(
            {
                "app": settings.app_name,
                "adapter_mode": settings.adapter_mode,
                "message": "Frontend not built yet. Run the Vite dev server or build frontend/dist.",
            }
        )

    @app.get("/{full_path:path}", response_model=None)
    def spa_fallback(full_path: str, request: Request):
        if full_path.startswith("api"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        maybe_file = frontend_file(settings.frontend_dist_path, full_path)
        if maybe_file is not None:
            return maybe_file
        return JSONResponse({"detail": "Not found"}, status_code=404)

    return app


app = create_app()
