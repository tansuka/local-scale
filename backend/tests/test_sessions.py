from __future__ import annotations

import time


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
