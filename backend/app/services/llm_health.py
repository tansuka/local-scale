from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.models import AppSettings, Measurement, Profile, utcnow
from app.repositories.app_settings import get_app_settings, update_app_settings
from app.repositories.health_analyses import (
    get_profile_health_analysis,
    save_profile_health_analysis,
)
from app.repositories.measurements import list_measurements
from app.schemas import HealthAnalysisRead, LlmSettingsRead, LlmSettingsUpdateRequest
from app.services.metrics import age_on

ALLOWED_CONCERN_LEVELS = {"low", "moderate", "high"}
TRACKED_METRICS = (
    "weight_kg",
    "waist_cm",
    "bmi",
    "fat_pct",
    "skeletal_muscle_weight_kg",
    "skeletal_muscle_pct",
    "muscle_pct",
    "visceral_fat",
    "visceral_adiposity_index",
    "water_pct",
    "bmr_kcal",
    "metabolic_age",
    "body_age",
)


@dataclass(frozen=True, slots=True)
class PromptState:
    path: Path
    text: str | None
    sha256: str | None
    loaded: bool
    error: str | None = None


class LlmHealthAnalyzer:
    def __init__(
        self,
        *,
        prompt_path: Path,
        http_client_factory: Any | None = None,
    ) -> None:
        self._prompt = self._load_prompt(prompt_path)
        self._http_client_factory = http_client_factory or (
            lambda: httpx.Client(timeout=30.0, follow_redirects=True)
        )

    def get_settings_view(self, db: Session) -> LlmSettingsRead:
        settings = get_app_settings(db)
        return LlmSettingsRead(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            has_api_key=bool(settings.llm_api_key),
            api_key_preview=_mask_api_key(settings.llm_api_key),
            prompt_path=str(self._prompt.path),
            prompt_loaded=self._prompt.loaded,
            prompt_error=self._prompt.error,
        )

    def save_settings(
        self,
        db: Session,
        payload: LlmSettingsUpdateRequest,
    ) -> LlmSettingsRead:
        api_key = payload.api_key.strip() if payload.api_key is not None else None
        update_app_settings(
            db,
            llm_base_url=payload.base_url.strip(),
            llm_model=payload.model.strip(),
            api_key=api_key if api_key else None,
            clear_api_key=payload.clear_api_key,
        )
        return self.get_settings_view(db)

    def resolve_analysis(
        self,
        db: Session,
        profile: Profile,
        *,
        force_refresh: bool = False,
    ) -> HealthAnalysisRead:
        measurements_desc = list_measurements(db, profile_id=profile.id, limit=7)
        if not measurements_desc:
            return HealthAnalysisRead(status="no_data")

        app_settings = get_app_settings(db)
        cached = get_profile_health_analysis(db, profile.id)
        measurement_ids = [measurement.id for measurement in measurements_desc]
        measurement_count = len(measurement_ids)
        latest_measurement_id = measurement_ids[0]

        if not _is_provider_configured(app_settings):
            return HealthAnalysisRead(
                status="not_configured",
                measurement_count=measurement_count,
                error_message="Set the LLM base URL and model in the admin panel to enable analysis.",
            )

        cache_matches = cached is not None and self._cache_matches(
            cached_measurement_ids=list(cached.measurement_ids_json or []),
            current_measurement_ids=measurement_ids,
            cached_latest_measurement_id=cached.latest_measurement_id,
            latest_measurement_id=latest_measurement_id,
            cached_prompt_hash=cached.prompt_hash,
            settings_updated_at=cached.settings_updated_at,
            current_settings_updated_at=app_settings.updated_at,
        )

        if not force_refresh and cache_matches and cached.summary:
            return _analysis_to_schema(cached, status="ready")

        ordered_measurements = list(reversed(measurements_desc))

        if not self._prompt.loaded:
            return self._cached_or_error(
                db,
                profile_id=profile.id,
                cached=cached,
                latest_measurement_id=latest_measurement_id,
                measurement_ids=measurement_ids,
                measurement_count=measurement_count,
                settings_updated_at=app_settings.updated_at,
                error_message=self._prompt.error or "Prompt file could not be loaded.",
            )

        try:
            generated = self._generate_analysis(
                profile=profile,
                measurements=ordered_measurements,
                app_settings=app_settings,
            )
        except Exception as exc:  # pragma: no cover - exercised via tests with concrete errors
            return self._cached_or_error(
                db,
                profile_id=profile.id,
                cached=cached,
                latest_measurement_id=latest_measurement_id,
                measurement_ids=measurement_ids,
                measurement_count=measurement_count,
                settings_updated_at=app_settings.updated_at,
                error_message=str(exc),
            )

        stored = save_profile_health_analysis(
            db,
            profile_id=profile.id,
            latest_measurement_id=latest_measurement_id,
            measurement_ids=measurement_ids,
            measurement_count=measurement_count,
            prompt_hash=self._prompt.sha256,
            settings_updated_at=app_settings.updated_at,
            summary=generated["summary"],
            concern_level=generated["concern_level"],
            highlights=generated["highlights"],
            generated_at=utcnow(),
            is_stale=False,
            error_message=None,
        )
        return _analysis_to_schema(stored, status="ready")

    def _cached_or_error(
        self,
        db: Session,
        *,
        profile_id: int,
        cached: Any,
        latest_measurement_id: int,
        measurement_ids: list[int],
        measurement_count: int,
        settings_updated_at: datetime | None,
        error_message: str,
    ) -> HealthAnalysisRead:
        if cached is not None and cached.summary:
            stored = save_profile_health_analysis(
                db,
                profile_id=profile_id,
                latest_measurement_id=latest_measurement_id,
                measurement_ids=measurement_ids,
                measurement_count=measurement_count,
                prompt_hash=self._prompt.sha256,
                settings_updated_at=settings_updated_at,
                summary=cached.summary,
                concern_level=cached.concern_level,
                highlights=list(cached.highlights_json or []),
                generated_at=cached.generated_at,
                is_stale=True,
                error_message=error_message,
            )
            return _analysis_to_schema(stored, status="ready")

        return HealthAnalysisRead(
            status="error",
            measurement_count=measurement_count,
            error_message=error_message,
        )

    def _cache_matches(
        self,
        *,
        cached_measurement_ids: list[int],
        current_measurement_ids: list[int],
        cached_latest_measurement_id: int | None,
        latest_measurement_id: int,
        cached_prompt_hash: str | None,
        settings_updated_at: datetime | None,
        current_settings_updated_at: datetime | None,
    ) -> bool:
        return (
            cached_measurement_ids == current_measurement_ids
            and cached_latest_measurement_id == latest_measurement_id
            and cached_prompt_hash == self._prompt.sha256
            and settings_updated_at == current_settings_updated_at
        )

    def _generate_analysis(
        self,
        *,
        profile: Profile,
        measurements: list[Measurement],
        app_settings: AppSettings,
    ) -> dict[str, Any]:
        if self._prompt.text is None:
            raise RuntimeError("Prompt is not loaded.")

        request_payload = self._build_request_payload(profile=profile, measurements=measurements)
        completion_text = self._request_completion(
            prompt=self._prompt.text,
            request_payload=request_payload,
            app_settings=app_settings,
        )
        return self._parse_completion_payload(completion_text)

    def _build_request_payload(
        self,
        *,
        profile: Profile,
        measurements: list[Measurement],
    ) -> dict[str, Any]:
        latest = measurements[-1]
        oldest = measurements[0]
        age_years = age_on(profile.birth_date, latest.measured_at.date())
        return {
            "profile": {
                "id": profile.id,
                "name": profile.name,
                "sex": profile.sex,
                "age_years": age_years,
                "height_cm": profile.height_cm,
            },
            "measurement_count": len(measurements),
            "latest_measurement": self._measurement_payload(latest),
            "trend_deltas": self._measurement_deltas(oldest, latest),
            "measurements": [self._measurement_payload(measurement) for measurement in measurements],
        }

    def _measurement_payload(self, measurement: Measurement) -> dict[str, Any]:
        payload = {
            "id": measurement.id,
            "measured_at": measurement.measured_at.isoformat(),
            "status_by_metric": dict(measurement.status_by_metric or {}),
        }
        for metric in TRACKED_METRICS:
            value = getattr(measurement, metric)
            if value is not None:
                payload[metric] = value
        return payload

    def _measurement_deltas(self, oldest: Measurement, latest: Measurement) -> dict[str, float]:
        deltas: dict[str, float] = {}
        for metric in TRACKED_METRICS:
            oldest_value = getattr(oldest, metric)
            latest_value = getattr(latest, metric)
            if oldest_value is None or latest_value is None:
                continue
            deltas[metric] = round(float(latest_value) - float(oldest_value), 2)
        return deltas

    def _request_completion(
        self,
        *,
        prompt: str,
        request_payload: dict[str, Any],
        app_settings: AppSettings,
    ) -> str:
        headers = {"Content-Type": "application/json"}
        if app_settings.llm_api_key:
            headers["Authorization"] = f"Bearer {app_settings.llm_api_key}"
        body = {
            "model": app_settings.llm_model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": (
                        "Analyze the following structured body-composition history. "
                        "Return JSON only with keys summary, concern_level, and highlights. "
                        "concern_level must be one of: low, moderate, high. "
                        "highlights must be an array of 1 to 3 short strings.\n\n"
                        f"{json.dumps(request_payload, separators=(',', ':'), ensure_ascii=True)}"
                    ),
                },
            ],
        }
        url = f"{app_settings.llm_base_url.rstrip('/')}/chat/completions"
        with self._http_client_factory() as client:
            response = client.post(url, headers=headers, json=body)
            response.raise_for_status()
            payload = response.json()
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("LLM response did not include any choices.")
        message = choices[0].get("message", {})
        content = message.get("content")
        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(str(item.get("text", "")))
            content = "\n".join(part for part in text_parts if part)
        if not isinstance(content, str) or not content.strip():
            raise ValueError("LLM response content was empty.")
        return content.strip()

    def _parse_completion_payload(self, completion_text: str) -> dict[str, Any]:
        try:
            payload = json.loads(completion_text)
        except json.JSONDecodeError as exc:
            raise ValueError("LLM response was not valid JSON.") from exc
        summary = str(payload.get("summary", "")).strip()
        concern_level = str(payload.get("concern_level", "")).strip().lower()
        highlights_raw = payload.get("highlights", [])
        if not summary:
            raise ValueError("LLM response did not include a summary.")
        if concern_level not in ALLOWED_CONCERN_LEVELS:
            raise ValueError("LLM response concern_level must be low, moderate, or high.")
        if not isinstance(highlights_raw, list):
            raise ValueError("LLM response highlights must be an array.")
        highlights = [str(item).strip() for item in highlights_raw if str(item).strip()]
        if not highlights:
            raise ValueError("LLM response did not include any highlights.")
        return {
            "summary": summary,
            "concern_level": concern_level,
            "highlights": highlights[:3],
        }

    @staticmethod
    def _load_prompt(prompt_path: Path) -> PromptState:
        try:
            text = prompt_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return PromptState(
                path=prompt_path,
                text=None,
                sha256=None,
                loaded=False,
                error=f"Prompt file not found at {prompt_path}.",
            )
        except OSError as exc:
            return PromptState(
                path=prompt_path,
                text=None,
                sha256=None,
                loaded=False,
                error=f"Prompt file could not be read: {exc}.",
            )
        if not text:
            return PromptState(
                path=prompt_path,
                text=None,
                sha256=None,
                loaded=False,
                error=f"Prompt file at {prompt_path} is empty.",
            )
        return PromptState(
            path=prompt_path,
            text=text,
            sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            loaded=True,
            error=None,
        )


def _analysis_to_schema(analysis: Any, *, status: str) -> HealthAnalysisRead:
    return HealthAnalysisRead(
        status=status,
        summary=analysis.summary,
        concern_level=analysis.concern_level,
        highlights=list(analysis.highlights_json or []),
        generated_at=analysis.generated_at,
        measurement_count=analysis.measurement_count,
        is_stale=bool(analysis.is_stale),
        error_message=analysis.error_message,
    )


def _mask_api_key(api_key: str | None) -> str | None:
    if not api_key:
        return None
    if len(api_key) <= 4:
        return "*" * len(api_key)
    return f"{'*' * max(len(api_key) - 4, 4)}{api_key[-4:]}"


def _is_provider_configured(settings: AppSettings) -> bool:
    return bool(settings.llm_base_url.strip() and settings.llm_model.strip())
