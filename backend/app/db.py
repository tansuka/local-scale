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
                self._ensure_column(
                    connection,
                    table_name="profile_health_analyses",
                    column_name="advice",
                    column_definition="TEXT",
                )
                self._migrate_profile_waist_to_measurements(connection)
                # Apple Health snapshot upsert-by-date migration
                self._ensure_column(
                    connection,
                    table_name="apple_health_snapshots",
                    column_name="snapshot_date",
                    column_definition="DATE",
                )
                self._ensure_column(
                    connection,
                    table_name="apple_health_snapshots",
                    column_name="updated_at",
                    column_definition="DATETIME",
                )
                self._compact_apple_health_snapshots(connection)

    @staticmethod
    def _ensure_column(connection, *, table_name: str, column_name: str, column_definition: str) -> None:
        try:
            rows = connection.execute(text(f"PRAGMA table_info({table_name})")).mappings().all()
        except Exception:
            return
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

    @staticmethod
    def _compact_apple_health_snapshots(connection) -> None:
        """Backfill snapshot_date and deduplicate: keep newest row per (profile_id, date)."""
        from app.core.config import get_settings
        from zoneinfo import ZoneInfo
        from datetime import datetime as _dt, timezone as _tz

        # Check if there are any rows that still need backfill
        needs_backfill = connection.execute(
            text("SELECT COUNT(*) FROM apple_health_snapshots WHERE snapshot_date IS NULL")
        ).scalar()
        if not needs_backfill:
            return

        display_tz = ZoneInfo(get_settings().display_timezone)

        # 1. Backfill snapshot_date and updated_at for existing rows
        rows = connection.execute(
            text("SELECT id, captured_at FROM apple_health_snapshots WHERE snapshot_date IS NULL")
        ).mappings().all()

        for row in rows:
            captured_raw = row["captured_at"]
            if isinstance(captured_raw, str):
                try:
                    captured = _dt.fromisoformat(captured_raw.replace("Z", "+00:00"))
                except ValueError:
                    captured = _dt.now(_tz.utc)
            elif isinstance(captured_raw, _dt):
                captured = captured_raw if captured_raw.tzinfo else captured_raw.replace(tzinfo=_tz.utc)
            else:
                captured = _dt.now(_tz.utc)

            local_date = captured.astimezone(display_tz).date().isoformat()
            connection.execute(
                text(
                    "UPDATE apple_health_snapshots "
                    "SET snapshot_date = :sd, updated_at = COALESCE(updated_at, captured_at) "
                    "WHERE id = :id"
                ),
                {"sd": local_date, "id": row["id"]},
            )

        # 2. Delete duplicates: keep the row with the latest captured_at per (profile_id, snapshot_date)
        connection.execute(
            text(
                """
                DELETE FROM apple_health_snapshots
                WHERE id NOT IN (
                    SELECT id FROM (
                        SELECT id, ROW_NUMBER() OVER (
                            PARTITION BY profile_id, snapshot_date
                            ORDER BY captured_at DESC
                        ) AS rn
                        FROM apple_health_snapshots
                    )
                    WHERE rn = 1
                )
                """
            )
        )
