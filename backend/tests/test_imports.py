from __future__ import annotations

from pathlib import Path


def test_import_preview_and_commit(client):
    repo_root = Path(__file__).resolve().parents[2]
    sample_csv = repo_root / "fixtures" / "imports" / "sample_import.csv"

    with sample_csv.open("rb") as handle:
        preview = client.post(
            "/api/imports/csv/preview",
            files={"file": ("sample_import.csv", handle, "text/csv")},
        )
    assert preview.status_code == 200
    assert preview.json()["rows"][0]["row_number"] == 1

    with sample_csv.open("rb") as handle:
        commit = client.post(
            "/api/imports/csv/commit",
            files={"file": ("sample_import.csv", handle, "text/csv")},
        )
    assert commit.status_code == 200
    payload = commit.json()
    assert payload["imported"] >= 4
    assert payload["skipped"] == 0


def test_patch_measurement_waist(client):
    dashboard = client.get("/api/dashboard")
    measurement = dashboard.json()["measurements"][0]

    response = client.patch(
        f"/api/measurements/{measurement['id']}",
        json={"waist_cm": 86},
    )

    assert response.status_code == 200
    assert response.json()["waist_cm"] == 86


def test_patch_measurement_recomputes_visceral_index(client):
    dashboard = client.get("/api/dashboard")
    measurement = dashboard.json()["measurements"][0]

    response = client.patch(
        f"/api/measurements/{measurement['id']}",
        json={
            "waist_cm": 84,
            "triglycerides_mmol_l": 1.1,
            "hdl_mmol_l": 1.4,
        },
    )

    assert response.status_code == 200
    assert response.json()["visceral_adiposity_index"] is not None
    assert response.json()["source_metric_map"]["visceral_adiposity_index"] == "vai_estimated"


def test_update_profile(client):
    dashboard = client.get("/api/dashboard")
    profile = dashboard.json()["profiles"][0]
    response = client.put(
        f"/api/profiles/{profile['id']}",
        json={
            "name": profile["name"],
            "sex": profile["sex"],
            "birth_date": profile["birth_date"],
            "height_cm": 185,
            "units": profile["units"],
            "color": "#1d4ed8",
            "notes": "Updated via test",
        },
    )
    assert response.status_code == 200
    assert response.json()["height_cm"] == 185
    assert response.json()["color"] == "#1d4ed8"
