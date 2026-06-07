"""Tests for Apple Health sync and snapshot endpoints."""
from __future__ import annotations

from fastapi.testclient import TestClient


SNAPSHOT_PAYLOAD = {
    "captured_at": "2026-06-07T10:00:00Z",
    "period_start": "2026-06-01T00:00:00Z",
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


def test_sync_deduplicates_by_captured_at(client: TestClient) -> None:
    profile_id = _get_profile_id(client)
    resp1 = client.post(
        "/api/apple-health/sync",
        json={"profile_id": profile_id, "snapshot": SNAPSHOT_PAYLOAD},
    )
    assert resp1.status_code == 201
    first_id = resp1.json()["id"]

    # Same captured_at → should return duplicate status
    resp2 = client.post(
        "/api/apple-health/sync",
        json={"profile_id": profile_id, "snapshot": SNAPSHOT_PAYLOAD},
    )
    assert resp2.status_code == 201
    body2 = resp2.json()
    assert body2["status"] == "duplicate"
    assert body2["id"] == first_id


def test_sync_allows_different_captured_at(client: TestClient) -> None:
    profile_id = _get_profile_id(client)
    client.post(
        "/api/apple-health/sync",
        json={"profile_id": profile_id, "snapshot": SNAPSHOT_PAYLOAD},
    )
    different_payload = {**SNAPSHOT_PAYLOAD, "captured_at": "2026-06-06T10:00:00Z"}
    resp = client.post(
        "/api/apple-health/sync",
        json={"profile_id": profile_id, "snapshot": different_payload},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "ok"


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
    assert "captured_at" in first
    assert "payload" in first


def test_get_snapshots_empty_for_unknown_profile(client: TestClient) -> None:
    resp = client.get("/api/apple-health/snapshots", params={"profile_id": 999999})
    assert resp.status_code == 200
    assert resp.json() == []
