from __future__ import annotations

from collections.abc import Generator

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db import Database
from app.services.events import EventBroker
from app.services.sessions import SessionManager


def get_db(request: Request) -> Generator[Session, None, None]:
    database: Database = request.app.state.db
    yield from database.session()


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_session_manager(request: Request) -> SessionManager:
    return request.app.state.session_manager


def get_events(request: Request) -> EventBroker:
    return request.app.state.events
