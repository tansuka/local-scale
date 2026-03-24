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
                    table_name="measurements",
                    column_name="waist_cm",
                    column_definition="FLOAT",
                )
                self._ensure_column(
                    connection,
                    table_name="measurements",
                    column_name="triglycerides_mmol_l",
                    column_definition="FLOAT",
                )
                self._ensure_column(
                    connection,
                    table_name="measurements",
                    column_name="hdl_mmol_l",
                    column_definition="FLOAT",
                )
                self._ensure_column(
                    connection,
                    table_name="measurements",
                    column_name="visceral_adiposity_index",
                    column_definition="FLOAT",
                )
                self._migrate_profile_waist_to_measurements(connection)

    @staticmethod
    def _ensure_column(connection, *, table_name: str, column_name: str, column_definition: str) -> None:
        rows = connection.execute(text(f"PRAGMA table_info({table_name})")).mappings().all()
        existing = {str(row["name"]) for row in rows}
        if column_name in existing:
            return
        connection.execute(
            text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")
        )

    @staticmethod
    def _migrate_profile_waist_to_measurements(connection) -> None:
        profile_columns = {
            str(row["name"])
            for row in connection.execute(text("PRAGMA table_info(profiles)")).mappings().all()
        }
        measurement_columns = {
            str(row["name"])
            for row in connection.execute(text("PRAGMA table_info(measurements)")).mappings().all()
        }
        if "waist_cm" not in profile_columns or "waist_cm" not in measurement_columns:
            return
        connection.execute(
            text(
                """
                UPDATE measurements
                SET waist_cm = (
                    SELECT profiles.waist_cm
                    FROM profiles
                    WHERE profiles.id = measurements.profile_id
                )
                WHERE waist_cm IS NULL
                  AND profile_id IN (
                    SELECT id
                    FROM profiles
                    WHERE waist_cm IS NOT NULL
                  )
                """
            )
        )
