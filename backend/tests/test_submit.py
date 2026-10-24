from __future__ import annotations


def _selected_profile_id(client) -> int:
    return client.get("/api/dashboard").json()["selected_profile_id"]


def test_submit_keeps_scale_reported_body_composition(client):
    profile_id = _selected_profile_id(client)

    response = client.post(
        "/api/measurements/submit",
        json={
            "profile_id": profile_id,
            "measured_at": "2026-10-20T07:15:00Z",
            "weight_kg": 78.2,
            "fat_pct": 18.4,
            "water_pct": 63.9,
            "muscle_pct": 36.3,
            "bone_weight_kg": 3.0,
            "raw_payload_json": {"parser": "medisana_bs44x_gatt_v1"},
            "source_metric_map": {
                "weight_kg": "medisana_bs44x_gatt_v1",
                "fat_pct": "medisana_bs44x_gatt_v1",
                "water_pct": "medisana_bs44x_gatt_v1",
                "muscle_pct": "medisana_bs44x_gatt_v1",
                "bone_weight_kg": "medisana_bs44x_gatt_v1",
            },
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["fat_pct"] == 18.4
    assert body["water_pct"] == 63.9
    assert body["muscle_pct"] == 36.3
    assert body["bone_weight_kg"] == 3.0
    assert body["fat_weight_kg"] == round(78.2 * 18.4 / 100, 2)
    assert body["source_metric_map"]["fat_pct"] == "medisana_bs44x_gatt_v1"


def test_submit_without_body_composition_still_estimates(client):
    profile_id = _selected_profile_id(client)

    response = client.post(
        "/api/measurements/submit",
        json={
            "profile_id": profile_id,
            "measured_at": "2026-10-21T07:15:00Z",
            "weight_kg": 78.2,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["fat_pct"] is not None
    assert body["source_metric_map"]["fat_pct"] != "medisana_bs44x_gatt_v1"


def test_submit_rejects_out_of_range_body_composition(client):
    profile_id = _selected_profile_id(client)

    response = client.post(
        "/api/measurements/submit",
        json={
            "profile_id": profile_id,
            "measured_at": "2026-10-22T07:15:00Z",
            "weight_kg": 78.2,
            "fat_pct": 140.0,
        },
    )

    assert response.status_code == 422


def test_submit_stores_offset_timestamps_as_the_same_instant(client):
    profile_id = _selected_profile_id(client)

    response = client.post(
        "/api/measurements/submit",
        json={
            "profile_id": profile_id,
            "measured_at": "2026-10-21T08:00:00+02:00",
            "weight_kg": 80.0,
        },
    )

    assert response.status_code == 201
    # Served in Europe/Amsterdam, which is +02:00 on this date: same instant as sent.
    assert response.json()["measured_at"] == "2026-10-21T08:00:00+02:00"

    # The same instant written in UTC is recognised as a duplicate.
    duplicate = client.post(
        "/api/measurements/submit",
        json={
            "profile_id": profile_id,
            "measured_at": "2026-10-21T06:00:00Z",
            "weight_kg": 80.0,
        },
    )
    assert duplicate.status_code == 409
