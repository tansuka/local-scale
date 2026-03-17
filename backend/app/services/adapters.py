from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.models import Measurement, Profile


class ScaleAdapterError(RuntimeError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class ScaleAdapter(ABC):
    @abstractmethod
    async def capture_measurement(
        self,
        profile: Profile,
        recent_measurements: list[Measurement],
    ) -> dict[str, Any]:
        raise NotImplementedError


class ReplayAdapter(ScaleAdapter):
    def __init__(self, settings: Settings) -> None:
        self._delay = settings.replay_delay_seconds
        self._fixture = self._load_fixture(settings.replay_fixture_path)
        self._cursor = 0

    def _load_fixture(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {
                "patterns": [
                    {
                        "weight_delta": 0.2,
                        "fat_pct_delta": -0.1,
                        "water_pct_delta": 0.1,
                        "muscle_pct_delta": 0.05,
                        "skeletal_muscle_pct_delta": 0.04,
                        "visceral_fat_delta": 0.0,
                    }
                ]
            }
        return json.loads(path.read_text())

    def _default_baseline(self, profile: Profile) -> dict[str, float]:
        if profile.sex.lower().startswith("m"):
            return {
                "weight_kg": 82.0,
                "fat_pct": 19.5,
                "water_pct": 55.0,
                "muscle_pct": 47.0,
                "skeletal_muscle_pct": 41.0,
                "visceral_fat": 10.0,
            }
        return {
            "weight_kg": 67.0,
            "fat_pct": 28.0,
            "water_pct": 50.5,
            "muscle_pct": 34.0,
            "skeletal_muscle_pct": 31.5,
            "visceral_fat": 8.0,
        }

    async def capture_measurement(
        self,
        profile: Profile,
        recent_measurements: list[Measurement],
    ) -> dict[str, Any]:
        await asyncio.sleep(self._delay)
        pattern = self._fixture.get("patterns", [{}])[self._cursor % len(self._fixture.get("patterns", [{}]))]
        self._cursor += 1
        latest = recent_measurements[0] if recent_measurements else None
        baseline = (
            {
                "weight_kg": latest.weight_kg,
                "fat_pct": latest.fat_pct or self._default_baseline(profile)["fat_pct"],
                "water_pct": latest.water_pct or self._default_baseline(profile)["water_pct"],
                "muscle_pct": latest.muscle_pct or self._default_baseline(profile)["muscle_pct"],
                "skeletal_muscle_pct": latest.skeletal_muscle_pct or self._default_baseline(profile)["skeletal_muscle_pct"],
                "visceral_fat": latest.visceral_fat or self._default_baseline(profile)["visceral_fat"],
            }
            if latest
            else self._default_baseline(profile)
        )

        return {
            "measured_at": datetime.now(timezone.utc),
            "measurement_date": date.today(),
            "source": "replay",
            "weight_kg": round(baseline["weight_kg"] + pattern.get("weight_delta", 0.2), 2),
            "fat_pct": round(baseline["fat_pct"] + pattern.get("fat_pct_delta", -0.05), 2),
            "water_pct": round(baseline["water_pct"] + pattern.get("water_pct_delta", 0.08), 2),
            "muscle_pct": round(baseline["muscle_pct"] + pattern.get("muscle_pct_delta", 0.03), 2),
            "skeletal_muscle_pct": round(
                baseline["skeletal_muscle_pct"] + pattern.get("skeletal_muscle_pct_delta", 0.02),
                2,
            ),
            "visceral_fat": round(
                baseline["visceral_fat"] + pattern.get("visceral_fat_delta", 0.0),
                1,
            ),
            "raw_payload_json": {
                "adapter": "replay",
                "pattern_index": self._cursor - 1,
                "profile_name": profile.name,
            },
            "source_metric_map": {
                "weight_kg": "replay",
                "fat_pct": "replay",
                "water_pct": "replay",
                "muscle_pct": "replay",
                "skeletal_muscle_pct": "replay",
                "visceral_fat": "replay",
            },
        }


class LiveBleAdapter(ScaleAdapter):
    def __init__(self, settings: Settings) -> None:
        self._target_names = settings.target_scale_names
        self._capture_dir = settings.ble_capture_dir

    @staticmethod
    def _hex_payload_map(values: dict[int, bytes] | None) -> dict[str, str]:
        if not values:
            return {}
        return {str(key): value.hex() for key, value in values.items()}

    @classmethod
    def _serialize_match(
        cls,
        device: Any,
        advertisement_data: Any | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": device.name or "Unknown",
            "address": device.address,
            "rssi": getattr(device, "rssi", None),
        }
        if advertisement_data is not None:
            payload["local_name"] = getattr(advertisement_data, "local_name", None)
            payload["service_uuids"] = list(getattr(advertisement_data, "service_uuids", []) or [])
            payload["service_data"] = {
                str(key): (
                    value.hex() if isinstance(value, (bytes, bytearray)) else str(value)
                )
                for key, value in (getattr(advertisement_data, "service_data", {}) or {}).items()
            }
            payload["manufacturer_data"] = cls._hex_payload_map(
                getattr(advertisement_data, "manufacturer_data", None)
            )
            payload["tx_power"] = getattr(advertisement_data, "tx_power", None)
            payload["platform_data"] = [
                item.hex() if isinstance(item, (bytes, bytearray)) else str(item)
                for item in (getattr(advertisement_data, "platform_data", []) or [])
            ]
        return payload

    def _write_capture(self, payload: dict[str, Any]) -> Path:
        self._capture_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        capture_path = self._capture_dir / f"ble-scan-{stamp}.json"
        capture_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
        return capture_path

    async def capture_measurement(
        self,
        profile: Profile,
        recent_measurements: list[Measurement],
    ) -> dict[str, Any]:
        try:
            from bleak import BleakScanner
        except ImportError as exc:  # pragma: no cover - depends on runtime
            raise ScaleAdapterError("Bleak is not installed in this environment.") from exc

        raw_devices: list[dict[str, Any]]
        matches: list[dict[str, Any]]
        try:
            discovered = await BleakScanner.discover(timeout=8.0, return_adv=True)
            raw_devices = []
            matches = []
            for device, advertisement_data in discovered.values():
                serialized = self._serialize_match(device, advertisement_data)
                raw_devices.append(serialized)
                if any(token.lower() in (device.name or "").lower() for token in self._target_names):
                    matches.append(serialized)
        except TypeError:
            devices = await BleakScanner.discover(timeout=8.0)
            raw_devices = [self._serialize_match(device) for device in devices]
            matches = [
                serialized
                for device, serialized in zip(devices, raw_devices, strict=False)
                if any(token.lower() in (device.name or "").lower() for token in self._target_names)
            ]

        capture_payload = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "profile": profile.name,
            "target_names": list(self._target_names),
            "matched_devices": matches,
            "all_devices": raw_devices,
        }
        capture_path = self._write_capture(capture_payload)
        details = {
            "profile": profile.name,
            "discovered_devices": matches,
            "capture_file": str(capture_path),
        }
        raise ScaleAdapterError(
            "Live Bluetooth discovery is wired up, but protocol decoding still needs a packet capture from the MiniPC target.",
            details=details,
        )


def build_scale_adapter(settings: Settings) -> ScaleAdapter:
    if settings.adapter_mode == "live":
        return LiveBleAdapter(settings)
    return ReplayAdapter(settings)
