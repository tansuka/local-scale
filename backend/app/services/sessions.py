from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db import Database
from app.models import WeighSession
from app.repositories.measurements import add_measurement, recent_measurements
from app.repositories.profiles import get_profile
from app.repositories.sessions import create_session, get_session, latest_session
from app.schemas import MeasurementRead, WeighSessionRead
from app.services.adapters import ScaleAdapter, ScaleAdapterError
from app.services.anomaly import anomaly_score, requires_confirmation
from app.services.events import EventBroker
from app.services.metrics import normalize_measurement


class SessionManager:
    def __init__(
        self,
        *,
        database: Database,
        adapter: ScaleAdapter,
        events: EventBroker,
        adapter_mode: str,
        session_timeout_seconds: int,
    ) -> None:
        self._database = database
        self._adapter = adapter
        self._events = events
        self._adapter_mode = adapter_mode
        self._session_timeout = session_timeout_seconds
        self._lock = asyncio.Lock()

    def latest(self, db: Session) -> WeighSession | None:
        return latest_session(db)

    async def start_session(self, db: Session, selected_profile_id: int) -> WeighSession:
        async with self._lock:
            started_at = datetime.now(timezone.utc)
            session = create_session(
                db,
                {
                    "id": uuid.uuid4().hex,
                    "selected_profile_id": selected_profile_id,
                    "status": "armed",
                    "adapter_mode": self._adapter_mode,
                    "started_at": started_at,
                    "expires_at": started_at + timedelta(seconds=self._session_timeout),
                    "requires_confirmation": False,
                },
            )
            asyncio.create_task(self._run_session(session.id))
            await self._events.broadcast(
                {"type": "session.updated", "session": WeighSessionRead.model_validate(session).model_dump(mode="json")}
            )
            return session

    async def _run_session(self, session_id: str) -> None:
        db = self._database.make_session()
        try:
            session = get_session(db, session_id)
            if session is None:
                return
            session.status = "capturing"
            db.commit()
            db.refresh(session)
            await self._events.broadcast(
                {"type": "session.updated", "session": WeighSessionRead.model_validate(session).model_dump(mode="json")}
            )

            profile = get_profile(db, session.selected_profile_id)
            if profile is None:
                raise ScaleAdapterError("Selected profile was not found.")

            recent = recent_measurements(db, profile.id, limit=14)
            raw_measurement = await self._adapter.capture_measurement(profile, recent)
            normalized = normalize_measurement(profile, raw_measurement)
            score = anomaly_score(recent, normalized)
            needs_confirmation = requires_confirmation(score, normalized, recent)
            stored = add_measurement(
                db,
                {
                    **normalized,
                    "profile_id": profile.id,
                    "assignment_state": "pending_confirmation" if needs_confirmation else "confirmed",
                    "confidence": round(max(0.05, 1.0 - score), 3),
                    "anomaly_score": score,
                    "note": (
                        "Needs confirmation because it looks unusual for the selected profile."
                        if needs_confirmation
                        else "Saved to the remembered profile."
                    ),
                },
            )
            session.status = "completed"
            session.completed_at = datetime.now(timezone.utc)
            session.measurement_id = stored.id
            session.anomaly_score = score
            session.requires_confirmation = needs_confirmation
            db.commit()
            db.refresh(session)
            await self._events.broadcast(
                {
                    "type": "measurement.created",
                    "measurement": MeasurementRead.model_validate(stored).model_dump(mode="json"),
                }
            )
            await self._events.broadcast(
                {"type": "session.updated", "session": WeighSessionRead.model_validate(session).model_dump(mode="json")}
            )
        except ScaleAdapterError as exc:
            session = get_session(db, session_id)
            if session is not None:
                session.status = "failed"
                session.completed_at = datetime.now(timezone.utc)
                session.error_message = str(exc)
                db.commit()
                db.refresh(session)
                await self._events.broadcast(
                    {
                        "type": "session.updated",
                        "session": WeighSessionRead.model_validate(session).model_dump(mode="json"),
                        "details": exc.details,
                    }
                )
        finally:
            db.close()
