from __future__ import annotations

from collections.abc import Generator

from starlette.requests import HTTPConnection
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db import Database
from app.services.events import EventBroker
from app.services.llm_health import LlmHealthAnalyzer
from app.services.sessions import SessionManager


def get_db(connection: HTTPConnection) -> Generator[Session, None, None]:
    database: Database = connection.app.state.db
    yield from database.session()


def get_settings(connection: HTTPConnection) -> Settings:
    return connection.app.state.settings


def get_session_manager(connection: HTTPConnection) -> SessionManager:
    return connection.app.state.session_manager


def get_events(connection: HTTPConnection) -> EventBroker:
    return connection.app.state.events


def get_health_analyzer(connection: HTTPConnection) -> LlmHealthAnalyzer:
    return connection.app.state.health_analyzer
