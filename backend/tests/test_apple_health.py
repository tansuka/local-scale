"""Tests for Apple Health sync and snapshot endpoints."""
from __future__ import annotations

from fastapi.testclient import TestClient


SNAPSHOT_PAYLOAD = {
    "captured_at": "2026-06-07T10:00:00Z",
    "period_start": "2026-06-07T00:00:00Z",
    "period_end": "2026-06-07T23:59:59Z",
    "daily_summaries": [
        {
            "date": "2026-06-07",
            "metrics": {
                "HKQuantityTypeIdentifierStepCount": 8500,
                "HKQuantityTypeIdentifierActiveEnergyBurned": 420,
            },
        }
    ],
    "latest_samples": {
        "HKQuantityTypeIdentifierRestingHeartRate": {"value": 58},
    },
}


def _get_profile_id(client: TestClient) -> int:
    """Return the first profile's id from the seeded demo data."""
    resp = client.get("/api/profiles")
    assert resp.status_code == 200
    profiles = resp.json()
    assert len(profiles) > 0
    return profiles[0]["id"]


# ── POST /api/apple-health/sync ───────────────────────────────────────────────


def test_sync_creates_snapshot(client: TestClient) -> None:
    profile_id = _get_profile_id(client)
    resp = client.post(
        "/api/apple-health/sync",
        json={"profile_id": profile_id, "snapshot": SNAPSHOT_PAYLOAD},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "ok"
    assert isinstance(body["id"], int)


def test_sync_rejects_unknown_profile(client: TestClient) -> None:
    resp = client.post(
        "/api/apple-health/sync",
        json={"profile_id": 999999, "snapshot": SNAPSHOT_PAYLOAD},
    )
    assert resp.status_code == 404


def test_sync_upserts_same_date(client: TestClient) -> None:
    """Two syncs on the same calendar day should update the same row, not create a duplicate."""
    profile_id = _get_profile_id(client)
    resp1 = client.post(
        "/api/apple-health/sync",
        json={"profile_id": profile_id, "snapshot": SNAPSHOT_PAYLOAD},
    )
    assert resp1.status_code == 201
    first_id = resp1.json()["id"]

    # Same date, different captured_at → should upsert
    later_payload = {**SNAPSHOT_PAYLOAD, "captured_at": "2026-06-07T14:00:00Z"}
    resp2 = client.post(
        "/api/apple-health/sync",
        json={"profile_id": profile_id, "snapshot": later_payload},
    )
    assert resp2.status_code == 201
    body2 = resp2.json()
    assert body2["status"] == "updated"
    assert body2["id"] == first_id


def test_sync_creates_separate_rows_for_different_dates(client: TestClient) -> None:
    """Syncs on different calendar days should create separate rows."""
    profile_id = _get_profile_id(client)
    client.post(
        "/api/apple-health/sync",
        json={"profile_id": profile_id, "snapshot": SNAPSHOT_PAYLOAD},
    )
    different_date_payload = {**SNAPSHOT_PAYLOAD, "captured_at": "2026-06-06T10:00:00Z"}
    resp = client.post(
        "/api/apple-health/sync",
        json={"profile_id": profile_id, "snapshot": different_date_payload},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "ok"


def test_sync_upsert_replaces_payload(client: TestClient) -> None:
    """When upserting, the payload should be fully replaced with the latest data."""
    profile_id = _get_profile_id(client)

    # First sync: steps = 3000
    payload_v1 = {
        **SNAPSHOT_PAYLOAD,
        "daily_summaries": [
            {"date": "2026-06-07", "metrics": {"HKQuantityTypeIdentifierStepCount": 3000}},
        ],
    }
    resp1 = client.post(
        "/api/apple-health/sync",
        json={"profile_id": profile_id, "snapshot": payload_v1},
    )
    assert resp1.json()["status"] == "ok"
    snapshot_id = resp1.json()["id"]

    # Second sync: steps = 8000 (same day, later captured_at)
    payload_v2 = {
        **SNAPSHOT_PAYLOAD,
        "captured_at": "2026-06-07T18:00:00Z",
        "daily_summaries": [
            {"date": "2026-06-07", "metrics": {"HKQuantityTypeIdentifierStepCount": 8000}},
        ],
    }
    resp2 = client.post(
        "/api/apple-health/sync",
        json={"profile_id": profile_id, "snapshot": payload_v2},
    )
    assert resp2.json()["status"] == "updated"
    assert resp2.json()["id"] == snapshot_id

    # Verify stored payload has the updated steps
    snapshots_resp = client.get(
        "/api/apple-health/snapshots", params={"profile_id": profile_id}
    )
    snapshots = snapshots_resp.json()
    # Find the snapshot for 2026-06-07
    day_snapshots = [s for s in snapshots if s.get("snapshot_date") == "2026-06-07"]
    assert len(day_snapshots) == 1
    stored_steps = day_snapshots[0]["payload"]["daily_summaries"][0]["metrics"][
        "HKQuantityTypeIdentifierStepCount"
    ]
    assert stored_steps == 8000


# ── GET /api/apple-health/snapshots ───────────────────────────────────────────


def test_get_snapshots_returns_list(client: TestClient) -> None:
    profile_id = _get_profile_id(client)
    # Insert a snapshot first
    client.post(
        "/api/apple-health/sync",
        json={"profile_id": profile_id, "snapshot": SNAPSHOT_PAYLOAD},
    )
    resp = client.get("/api/apple-health/snapshots", params={"profile_id": profile_id})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    first = data[0]
    assert "id" in first
    assert "snapshot_date" in first
    assert "captured_at" in first
    assert "updated_at" in first
    assert "payload" in first


def test_get_snapshots_empty_for_unknown_profile(client: TestClient) -> None:
    resp = client.get("/api/apple-health/snapshots", params={"profile_id": 999999})
    assert resp.status_code == 200
    assert resp.json() == []
