from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, text
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
        self._apply_additive_schema_upgrades()

    def session(self) -> Generator[Session, None, None]:
        db = self._sessionmaker()
        try:
            yield db
        finally:
            db.close()

    def make_session(self) -> Session:
        return self._sessionmaker()

    def _apply_additive_schema_upgrades(self) -> None:
        with self.engine.begin() as connection:
            dialect_name = self.engine.dialect.name
            if dialect_name == "sqlite":
                self._ensure_column(
                    connection,
                    table_name="profiles",
                    column_name="waist_cm",
                    column_definition="FLOAT",
                )

    @staticmethod
    def _ensure_column(connection, *, table_name: str, column_name: str, column_definition: str) -> None:
        rows = connection.execute(text(f"PRAGMA table_info({table_name})")).mappings().all()
        existing = {str(row["name"]) for row in rows}
        if column_name in existing:
            return
        connection.execute(
            text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")
        )
