from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.models import Base


class Database:
    def __init__(self, settings: Settings) -> None:
        connect_args = {}
        if settings.database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        self.engine = create_engine(settings.database_url, connect_args=connect_args)
        self._sessionmaker = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
        )

    def create_all(self) -> None:
        Base.metadata.create_all(self.engine)

    def session(self) -> Generator[Session, None, None]:
        db = self._sessionmaker()
        try:
            yield db
        finally:
            db.close()

    def make_session(self) -> Session:
        return self._sessionmaker()
