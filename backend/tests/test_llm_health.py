from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from app.models import Measurement
from app.repositories.app_settings import get_app_settings
from app.services.llm_health import PromptState


def _selected_profile_id(client) -> int:
    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    return int(dashboard.json()["selected_profile_id"])


def _add_measurement(client, profile_id: int, *, measured_at: datetime, weight_kg: float) -> None:
    with client.app.state.db.make_session() as db:
        db.add(
            Measurement(
                profile_id=profile_id,
                measured_at=measured_at,
                source="import",
                assignment_state="confirmed",
                confidence=1.0,
                anomaly_score=0.0,
                note="Added during test",
                weight_kg=weight_kg,
                bmi=24.0,
                fat_pct=20.0,
                water_pct=55.0,
                skeletal_muscle_pct=41.0,
                skeletal_muscle_weight_kg=30.0,
                muscle_pct=47.0,
                visceral_fat=9.0,
                status_by_metric={"bmi": "healthy"},
                source_metric_map={"weight_kg": "import"},
                raw_payload_json={"test": True},
            )
        )
        db.commit()


def _configure_llm(client) -> None:
    response = client.put(
        "/api/admin/llm-settings",
        json={
            "base_url": "http://llm.local/v1",
            "model": "mock-model",
            "api_key": "secret-1234",
        },
    )
    assert response.status_code == 200


def test_dashboard_reports_not_configured_analysis_by_default(client):
    response = client.get("/api/dashboard")

    assert response.status_code == 200
    assert response.json()["health_analysis"]["status"] == "not_configured"


def test_admin_settings_mask_and_preserve_api_key(client):
    _configure_llm(client)

    first_read = client.get("/api/admin/llm-settings")
    assert first_read.status_code == 200
    assert first_read.json()["has_api_key"] is True
    assert first_read.json()["api_key_preview"].endswith("1234")
    assert "secret-1234" not in first_read.text

    second_write = client.put(
        "/api/admin/llm-settings",
        json={"base_url": "http://llm.local/v1", "model": "next-model"},
    )
    assert second_write.status_code == 200

    with client.app.state.db.make_session() as db:
        settings = get_app_settings(db)
        assert settings.llm_model == "next-model"
        assert settings.llm_api_key == "secret-1234"


def test_manual_run_uses_latest_seven_measurements(client):
    profile_id = _selected_profile_id(client)
    _configure_llm(client)

    start = datetime(2026, 3, 11, 7, 0, tzinfo=timezone.utc)
    for index in range(5):
        _add_measurement(
            client,
            profile_id,
            measured_at=start + timedelta(days=index),
            weight_kg=82.0 + index,
        )

    captured_payload: dict[str, object] = {}
    analyzer = client.app.state.health_analyzer

    def fake_request_completion(*, request_payload, **_kwargs):
        captured_payload["payload"] = request_payload
        return json.dumps(
            {
                "summary": "Stable overall trend.",
                "concern_level": "low",
                "highlights": ["Weight is moving gradually.", "No abrupt red flags."],
            }
        )

    analyzer._request_completion = fake_request_completion

    response = client.post(f"/api/admin/profiles/{profile_id}/health-analysis/run")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["measurement_count"] == 7

    payload = captured_payload["payload"]
    assert isinstance(payload, dict)
    measurements = payload["measurements"]
    assert len(measurements) == 7
    assert [item["id"] for item in measurements] == sorted(
        [item["id"] for item in measurements],
    )[-7:]


def test_dashboard_returns_stale_cached_analysis_when_refresh_fails(client):
    profile_id = _selected_profile_id(client)
    _configure_llm(client)
    analyzer = client.app.state.health_analyzer

    analyzer._request_completion = lambda **_kwargs: json.dumps(
        {
            "summary": "Initial cached summary.",
            "concern_level": "moderate",
            "highlights": ["Baseline summary"],
        }
    )
    first_run = client.post(f"/api/admin/profiles/{profile_id}/health-analysis/run")
    assert first_run.status_code == 200

    _add_measurement(
        client,
        profile_id,
        measured_at=datetime(2026, 3, 20, 7, 0, tzinfo=timezone.utc),
        weight_kg=88.0,
    )

    def failing_request_completion(**_kwargs):
        raise RuntimeError("LLM backend is unavailable.")

    analyzer._request_completion = failing_request_completion

    dashboard = client.get(f"/api/dashboard?profile_id={profile_id}")
    assert dashboard.status_code == 200
    analysis = dashboard.json()["health_analysis"]
    assert analysis["status"] == "ready"
    assert analysis["is_stale"] is True
    assert analysis["summary"] == "Initial cached summary."
    assert "unavailable" in analysis["error_message"].lower()


def test_prompt_hash_change_invalidates_cache(client):
    profile_id = _selected_profile_id(client)
    _configure_llm(client)
    analyzer = client.app.state.health_analyzer

    analyzer._request_completion = lambda **_kwargs: json.dumps(
        {
            "summary": "Prompt version one.",
            "concern_level": "low",
            "highlights": ["Version one"],
        }
    )
    first_run = client.post(f"/api/admin/profiles/{profile_id}/health-analysis/run")
    assert first_run.status_code == 200

    analyzer._prompt = PromptState(
        path=analyzer._prompt.path,
        text="updated prompt",
        sha256="different-hash",
        loaded=True,
        error=None,
    )
    analyzer._request_completion = lambda **_kwargs: json.dumps(
        {
            "summary": "Prompt version two.",
            "concern_level": "low",
            "highlights": ["Version two"],
        }
    )

    dashboard = client.get(f"/api/dashboard?profile_id={profile_id}")
    assert dashboard.status_code == 200
    assert dashboard.json()["health_analysis"]["summary"] == "Prompt version two."
