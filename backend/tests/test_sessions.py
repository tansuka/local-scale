from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime

from app.services.sessions import SessionManager


def test_start_session_uses_selected_profile_flow(client):
    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    selected_profile_id = dashboard.json()["selected_profile_id"]

    start = client.post("/api/sessions/start", json={"selected_profile_id": selected_profile_id})
    assert start.status_code == 202
    assert start.json()["status"] == "armed"

    time.sleep(0.08)

    session = client.get("/api/sessions/current")
    assert session.status_code == 200
    assert session.json()["selected_profile_id"] == selected_profile_id
    assert session.json()["status"] in {"completed", "capturing"}

    measurements = client.get(f"/api/measurements?profile_id={selected_profile_id}")
    assert measurements.status_code == 200
    assert len(measurements.json()) >= 1


def test_delete_measurement(client):
    dashboard = client.get("/api/dashboard")
    selected_profile_id = dashboard.json()["selected_profile_id"]
    measurements = client.get(f"/api/measurements?profile_id={selected_profile_id}")
    measurement_id = measurements.json()[0]["id"]

    deleted = client.delete(f"/api/measurements/{measurement_id}")
    assert deleted.status_code == 204

    refreshed = client.get(f"/api/measurements?profile_id={selected_profile_id}")
    assert all(item["id"] != measurement_id for item in refreshed.json())


def test_start_session_surfaces_bluetooth_adapter_errors(client):
    dashboard = client.get("/api/dashboard")
    selected_profile_id = dashboard.json()["selected_profile_id"]

    async def fail_capture(*_args, **_kwargs):
        raise RuntimeError("No Bluetooth adapters found.")

    session_manager: SessionManager = client.app.state.session_manager
    original_capture = session_manager._adapter.capture_measurement
    session_manager._adapter.capture_measurement = fail_capture
    try:
        start = client.post("/api/sessions/start", json={"selected_profile_id": selected_profile_id})
        assert start.status_code == 202

        time.sleep(0.08)

        session = client.get("/api/sessions/current")
        assert session.status_code == 200
        assert session.json()["status"] == "failed"
        assert "No Bluetooth adapter was found on this machine." in session.json()["error_message"]
    finally:
        session_manager._adapter.capture_measurement = original_capture


def test_cancel_session_stops_active_capture(client):
    dashboard = client.get("/api/dashboard")
    selected_profile_id = dashboard.json()["selected_profile_id"]
    cancelled = threading.Event()

    async def slow_capture(*_args, **_kwargs):
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    session_manager: SessionManager = client.app.state.session_manager
    original_capture = session_manager._adapter.capture_measurement
    session_manager._adapter.capture_measurement = slow_capture
    try:
        start = client.post("/api/sessions/start", json={"selected_profile_id": selected_profile_id})
        assert start.status_code == 202
        session_id = start.json()["id"]

        time.sleep(0.08)

        cancelled_response = client.post(f"/api/sessions/{session_id}/cancel")
        assert cancelled_response.status_code == 200
        assert cancelled_response.json()["status"] == "cancelled"
        assert cancelled_response.json()["error_message"] == "Weigh-in cancelled."

        time.sleep(0.08)

        session = client.get("/api/sessions/current")
        assert session.status_code == 200
        assert session.json()["id"] == session_id
        assert session.json()["status"] == "cancelled"
        assert cancelled.wait(timeout=1.0) is True
    finally:
        session_manager._adapter.capture_measurement = original_capture


def test_start_session_serializes_utc_datetimes(client):
    dashboard = client.get("/api/dashboard")
    selected_profile_id = dashboard.json()["selected_profile_id"]

    start = client.post("/api/sessions/start", json={"selected_profile_id": selected_profile_id})
    payload = start.json()

    assert start.status_code == 202
    assert payload["started_at"].endswith("Z")
    assert payload["expires_at"].endswith("Z")


def test_start_session_uses_adapter_expected_capture_window(client):
    dashboard = client.get("/api/dashboard")
    selected_profile_id = dashboard.json()["selected_profile_id"]

    session_manager: SessionManager = client.app.state.session_manager
    original_expected_capture_seconds = session_manager._adapter.expected_capture_seconds
    session_manager._adapter.expected_capture_seconds = lambda: 3.0
    try:
        start = client.post("/api/sessions/start", json={"selected_profile_id": selected_profile_id})
        payload = start.json()

        started_at = datetime.fromisoformat(payload["started_at"].replace("Z", "+00:00"))
        expires_at = datetime.fromisoformat(payload["expires_at"].replace("Z", "+00:00"))

        assert start.status_code == 202
        assert (expires_at - started_at).total_seconds() == 3.0
    finally:
        session_manager._adapter.expected_capture_seconds = original_expected_capture_seconds
