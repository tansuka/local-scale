from __future__ import annotations

import ast
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
        self._target_names = tuple(token.lower() for token in settings.target_scale_names)
        self._target_addresses = {
            normalized
            for raw in settings.target_scale_addresses
            if (normalized := self._normalize_address(raw)) is not None
        }
        self._capture_dir = settings.ble_capture_dir
        self._scan_timeout_seconds = settings.ble_scan_timeout_seconds
        self._scan_rounds = settings.ble_scan_rounds
        self._scan_pause_seconds = settings.ble_scan_pause_seconds
        self._connect_timeout_seconds = settings.ble_connect_timeout_seconds
        self._connect_retries = settings.ble_connect_retries
        self._connect_retry_pause_seconds = settings.ble_connect_retry_pause_seconds
        self._notify_capture_seconds = settings.ble_notify_capture_seconds

    @staticmethod
    def _normalize_address(value: str | None) -> str | None:
        if not value:
            return None
        compact = "".join(char for char in value if char.isalnum()).lower()
        if len(compact) != 12:
            return value.strip().lower() or None
        return ":".join(compact[index : index + 2] for index in range(0, 12, 2))

    @staticmethod
    def _hex_payload_map(values: dict[int, bytes] | None) -> dict[str, str]:
        if not values:
            return {}
        return {str(key): value.hex() for key, value in values.items()}

    @staticmethod
    def _extract_rssi(device: Any, advertisement_data: Any | None = None) -> int | None:
        for source in (advertisement_data, device):
            if source is None:
                continue
            rssi = getattr(source, "rssi", None)
            if isinstance(rssi, int):
                return rssi

        platform_data = getattr(advertisement_data, "platform_data", None) or []
        for item in platform_data:
            candidate = item
            if isinstance(item, str) and item.startswith("{") and item.endswith("}"):
                try:
                    candidate = ast.literal_eval(item)
                except (ValueError, SyntaxError):
                    candidate = item
            if isinstance(candidate, dict) and isinstance(candidate.get("RSSI"), int):
                return candidate["RSSI"]
        return None

    def _match_reasons(self, payload: dict[str, Any]) -> list[str]:
        reasons: list[str] = []
        normalized_address = self._normalize_address(payload.get("address"))
        if normalized_address and normalized_address in self._target_addresses:
            reasons.append("target address")

        searchable_names = [
            str(payload.get("name") or "").lower(),
            str(payload.get("local_name") or "").lower(),
        ]
        if any(token in field for token in self._target_names for field in searchable_names if field):
            reasons.append("target name")
        return reasons

    def _candidate_score(self, payload: dict[str, Any]) -> tuple[int, int]:
        reasons = self._match_reasons(payload)
        score = 0
        if "target address" in reasons:
            score += 1000
        if "target name" in reasons:
            score += 500
        rssi = payload.get("rssi")
        if isinstance(rssi, int):
            score += 200 + rssi
        if payload.get("manufacturer_data"):
            score += 40
        if payload.get("service_data"):
            score += 20
        if payload.get("service_uuids"):
            score += 10
        return score, int(rssi) if isinstance(rssi, int) else -999

    @staticmethod
    def _device_key(payload: dict[str, Any], fallback: str) -> str:
        return str(payload.get("normalized_address") or payload.get("address") or fallback)

    def _merge_device_payload(
        self,
        existing: dict[str, Any] | None,
        payload: dict[str, Any],
        round_number: int,
    ) -> dict[str, Any]:
        if existing is None:
            merged = dict(payload)
            merged["seen_count"] = 1
            merged["seen_rounds"] = [round_number]
            if isinstance(payload.get("rssi"), int):
                merged["best_rssi"] = payload["rssi"]
            return merged

        merged = dict(existing)
        for key, value in payload.items():
            if value in (None, "", [], {}):
                continue
            merged[key] = value

        merged["seen_count"] = int(existing.get("seen_count", 0)) + 1
        merged["seen_rounds"] = sorted(
            {
                *[
                    int(value)
                    for value in existing.get("seen_rounds", [])
                    if isinstance(value, int | float)
                ],
                round_number,
            }
        )
        merged["match_reasons"] = sorted(
            {
                *[str(value) for value in existing.get("match_reasons", [])],
                *[str(value) for value in payload.get("match_reasons", [])],
            }
        )

        current_rssi = payload.get("rssi")
        best_rssi = existing.get("best_rssi")
        if isinstance(current_rssi, int):
            merged["last_rssi"] = current_rssi
            if not isinstance(best_rssi, int) or current_rssi > best_rssi:
                merged["best_rssi"] = current_rssi
                merged["rssi"] = current_rssi
            elif isinstance(best_rssi, int):
                merged["best_rssi"] = best_rssi
                merged["rssi"] = best_rssi
        elif isinstance(best_rssi, int):
            merged["best_rssi"] = best_rssi
            merged["rssi"] = best_rssi

        return merged

    async def _scan_once(
        self,
        scanner_cls: Any,
    ) -> tuple[
        list[dict[str, Any]],
        list[tuple[dict[str, Any], Any]],
        dict[str, Any] | None,
    ]:
        seen_devices: dict[str, dict[str, Any]] = {}
        matched_targets: dict[str, tuple[dict[str, Any], Any]] = {}
        match_event = asyncio.Event()
        live_protocol_capture: dict[str, Any] | None = None

        def detection_callback(device: Any, advertisement_data: Any) -> None:
            serialized = self._serialize_match(device, advertisement_data)
            serialized["match_reasons"] = self._match_reasons(serialized)
            device_key = self._device_key(serialized, f"detected-{len(seen_devices)}")
            seen_devices[device_key] = serialized
            if serialized["match_reasons"]:
                matched_targets[device_key] = (serialized, device)
                match_event.set()

        try:
            scanner = scanner_cls(detection_callback=detection_callback)
            scanner_running = False
            await scanner.start()
            scanner_running = True
            try:
                await asyncio.wait_for(match_event.wait(), timeout=self._scan_timeout_seconds)
            except TimeoutError:
                pass
            else:
                if matched_targets:
                    target_payload, target_device = max(
                        matched_targets.values(),
                        key=lambda record: self._candidate_score(record[0]),
                    )
                    live_protocol_capture = await self._capture_target_protocol(
                        target_device,
                        target_payload,
                        connection_targets=[("device", target_device)],
                    )
            finally:
                if scanner_running:
                    await scanner.stop()
            if seen_devices:
                return (
                    list(seen_devices.values()),
                    list(matched_targets.values()),
                    live_protocol_capture,
                )
        except TypeError:
            devices = await scanner_cls.discover(timeout=self._scan_timeout_seconds)
            round_payloads = [self._serialize_match(device) for device in devices]
            round_matches: list[tuple[dict[str, Any], Any]] = []
            for device, serialized in zip(devices, round_payloads, strict=False):
                serialized["match_reasons"] = self._match_reasons(serialized)
                if serialized["match_reasons"]:
                    round_matches.append((serialized, device))
            return round_payloads, round_matches, None
        except Exception:  # pragma: no cover - fallback for scanner backends that reject callbacks
            discovered = await scanner_cls.discover(
                timeout=self._scan_timeout_seconds,
                return_adv=True,
            )
            round_payloads = []
            round_matches = []
            for device, advertisement_data in discovered.values():
                serialized = self._serialize_match(device, advertisement_data)
                serialized["match_reasons"] = self._match_reasons(serialized)
                round_payloads.append(serialized)
                if serialized["match_reasons"]:
                    round_matches.append((serialized, device))
            return round_payloads, round_matches, None

        return list(seen_devices.values()), list(matched_targets.values()), live_protocol_capture

    async def _discover_targets(
        self,
        scanner_cls: Any,
    ) -> tuple[
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[tuple[dict[str, Any], Any]],
        int,
        dict[str, Any] | None,
    ]:
        seen_devices: dict[str, dict[str, Any]] = {}
        matched_targets: dict[str, tuple[dict[str, Any], Any]] = {}
        rounds_completed = 0
        protocol_capture: dict[str, Any] | None = None

        for round_number in range(1, self._scan_rounds + 1):
            rounds_completed = round_number
            round_payloads, round_matches, live_round_protocol_capture = await self._scan_once(
                scanner_cls
            )

            for index, payload in enumerate(round_payloads):
                device_key = self._device_key(payload, f"round-{round_number}-device-{index}")
                seen_devices[device_key] = self._merge_device_payload(
                    seen_devices.get(device_key),
                    payload,
                    round_number,
                )

            for index, (payload, device) in enumerate(round_matches):
                device_key = self._device_key(payload, f"round-{round_number}-match-{index}")
                merged_payload = seen_devices.get(device_key, payload)
                matched_targets[device_key] = (merged_payload, device)

            if live_round_protocol_capture is not None:
                protocol_capture = live_round_protocol_capture
            if matched_targets or round_number >= self._scan_rounds:
                break
            await asyncio.sleep(self._scan_pause_seconds)

        raw_devices = sorted(seen_devices.values(), key=self._candidate_score, reverse=True)
        matched_payloads = sorted(
            (payload for payload, _ in matched_targets.values()),
            key=self._candidate_score,
            reverse=True,
        )
        matched_records = sorted(
            matched_targets.values(),
            key=lambda record: self._candidate_score(record[0]),
            reverse=True,
        )
        return raw_devices, matched_payloads, matched_records, rounds_completed, protocol_capture

    @staticmethod
    def _iter_services(services: Any) -> list[Any]:
        known_services = getattr(services, "services", None)
        if isinstance(known_services, dict):
            return list(known_services.values())
        return list(services or [])

    @staticmethod
    def _serialize_descriptor(descriptor: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "handle": getattr(descriptor, "handle", None),
            "uuid": getattr(descriptor, "uuid", None),
        }
        description = getattr(descriptor, "description", None)
        if description:
            payload["description"] = str(description)
        return payload

    @classmethod
    async def _serialize_characteristic(
        cls,
        client: Any,
        characteristic: Any,
    ) -> dict[str, Any]:
        properties = sorted(str(prop) for prop in (getattr(characteristic, "properties", None) or []))
        payload: dict[str, Any] = {
            "uuid": getattr(characteristic, "uuid", None),
            "handle": getattr(characteristic, "handle", None),
            "properties": properties,
            "descriptors": [
                cls._serialize_descriptor(descriptor)
                for descriptor in (getattr(characteristic, "descriptors", None) or [])
            ],
        }
        description = getattr(characteristic, "description", None)
        if description:
            payload["description"] = str(description)

        if any(prop.lower() == "read" for prop in properties):
            try:
                read_value = await client.read_gatt_char(characteristic)
                payload["read_value_hex"] = bytes(read_value).hex()
            except Exception as exc:  # pragma: no cover - depends on runtime device behavior
                payload["read_error"] = {
                    "type": exc.__class__.__name__,
                    "message": str(exc),
                }
        return payload

    @classmethod
    async def _serialize_gatt_services(
        cls,
        client: Any,
        services: Any,
    ) -> list[dict[str, Any]]:
        serialized_services: list[dict[str, Any]] = []
        for service in cls._iter_services(services):
            service_payload: dict[str, Any] = {
                "uuid": getattr(service, "uuid", None),
                "handle": getattr(service, "handle", None),
                "characteristics": [],
            }
            description = getattr(service, "description", None)
            if description:
                service_payload["description"] = str(description)

            characteristics = []
            for characteristic in (getattr(service, "characteristics", None) or []):
                characteristics.append(await cls._serialize_characteristic(client, characteristic))
            service_payload["characteristics"] = characteristics
            serialized_services.append(service_payload)
        return serialized_services

    async def _capture_notifications(self, client: Any, services: Any) -> dict[str, Any]:
        packets: list[dict[str, Any]] = []
        dropped_packets = 0
        subscriptions: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        active_characteristics: list[Any] = []
        max_packets = 200

        def build_callback(characteristic_uuid: str):
            def _callback(_: Any, data: bytearray) -> None:
                nonlocal dropped_packets
                if len(packets) >= max_packets:
                    dropped_packets += 1
                    return
                packets.append(
                    {
                        "characteristic_uuid": characteristic_uuid,
                        "received_at": datetime.now(timezone.utc).isoformat(),
                        "data_hex": bytes(data).hex(),
                    }
                )

            return _callback

        for service in self._iter_services(services):
            for characteristic in (getattr(service, "characteristics", None) or []):
                properties = {
                    str(prop).lower()
                    for prop in (getattr(characteristic, "properties", None) or [])
                }
                if not properties.intersection({"notify", "indicate"}):
                    continue
                characteristic_uuid = str(getattr(characteristic, "uuid", "unknown"))
                try:
                    await client.start_notify(characteristic, build_callback(characteristic_uuid))
                    active_characteristics.append(characteristic)
                    subscriptions.append(
                        {
                            "characteristic_uuid": characteristic_uuid,
                            "properties": sorted(properties),
                        }
                    )
                except Exception as exc:  # pragma: no cover - depends on runtime device behavior
                    errors.append(
                        {
                            "characteristic_uuid": characteristic_uuid,
                            "stage": "start_notify",
                            "type": exc.__class__.__name__,
                            "message": str(exc),
                        }
                    )

        if active_characteristics:
            await asyncio.sleep(self._notify_capture_seconds)

        for characteristic in active_characteristics:
            try:
                await client.stop_notify(characteristic)
            except Exception as exc:  # pragma: no cover - depends on runtime device behavior
                errors.append(
                    {
                        "characteristic_uuid": str(getattr(characteristic, "uuid", "unknown")),
                        "stage": "stop_notify",
                        "type": exc.__class__.__name__,
                        "message": str(exc),
                    }
                )

        return {
            "capture_seconds": self._notify_capture_seconds if active_characteristics else 0,
            "subscribed_characteristics": subscriptions,
            "packet_count": len(packets),
            "dropped_packet_count": dropped_packets,
            "packets": packets,
            "errors": errors,
        }

    async def _capture_target_protocol(
        self,
        device: Any,
        matched_payload: dict[str, Any],
        *,
        connection_targets: list[tuple[str, Any]] | None = None,
    ) -> dict[str, Any]:
        try:
            from bleak import BleakClient
        except ImportError as exc:  # pragma: no cover - depends on runtime
            return {
                "attempted": False,
                "target_device": matched_payload,
                "error_type": exc.__class__.__name__,
                "error_message": "BleakClient is not installed in this environment.",
            }

        protocol_capture: dict[str, Any] = {
            "attempted": True,
            "target_device": matched_payload,
            "connect_timeout_seconds": self._connect_timeout_seconds,
            "connect_retries": self._connect_retries,
            "connect_retry_pause_seconds": self._connect_retry_pause_seconds,
            "notify_capture_seconds": self._notify_capture_seconds,
            "attempts": [],
        }
        normalized_address = self._normalize_address(matched_payload.get("address"))
        if connection_targets is None:
            connection_targets = []
            if normalized_address:
                connection_targets.append(("address", normalized_address))
            connection_targets.append(("device", device))

        for attempt_number in range(1, self._connect_retries + 1):
            attempt_payload: dict[str, Any] = {"attempt": attempt_number}
            for connection_method, connection_target in connection_targets:
                method_attempt = dict(attempt_payload)
                method_attempt["connection_method"] = connection_method
                method_attempt["connection_target"] = (
                    connection_target
                    if isinstance(connection_target, str)
                    else str(getattr(connection_target, "address", connection_target))
                )
                try:
                    try:
                        client = BleakClient(connection_target, timeout=self._connect_timeout_seconds)
                    except TypeError:  # pragma: no cover - compatibility fallback
                        client = BleakClient(connection_target)

                    async with client:
                        method_attempt["connected"] = bool(getattr(client, "is_connected", False))
                        try:
                            services = await client.get_services()
                        except Exception:  # pragma: no cover - compatibility fallback
                            services = getattr(client, "services", None)
                            if services is None:
                                raise

                        serialized_services = await self._serialize_gatt_services(client, services)
                        notification_capture = await self._capture_notifications(client, services)
                        method_attempt["service_count"] = len(serialized_services)
                        method_attempt["services"] = serialized_services
                        method_attempt["notification_capture"] = notification_capture
                        protocol_capture["attempts"].append(method_attempt)
                        protocol_capture["connected"] = method_attempt["connected"]
                        protocol_capture["service_count"] = method_attempt["service_count"]
                        protocol_capture["services"] = serialized_services
                        protocol_capture["notification_capture"] = notification_capture
                        protocol_capture["connection_method"] = connection_method
                        return protocol_capture
                except Exception as exc:  # pragma: no cover - depends on runtime device behavior
                    method_attempt["connected"] = False
                    method_attempt["error_type"] = exc.__class__.__name__
                    method_attempt["error_message"] = str(exc)
                    protocol_capture["attempts"].append(method_attempt)
                    protocol_capture["connected"] = False
                    protocol_capture["error_type"] = exc.__class__.__name__
                    protocol_capture["error_message"] = str(exc)
                    protocol_capture["connection_method"] = connection_method
            if attempt_number < self._connect_retries:
                await asyncio.sleep(self._connect_retry_pause_seconds)

        return protocol_capture

    @staticmethod
    def _merge_protocol_captures(
        first: dict[str, Any] | None,
        second: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if first is None:
            return second
        if second is None:
            return first

        merged = dict(second if second.get("connected") or not first.get("connected") else first)
        merged["attempts"] = [
            *list(first.get("attempts", []) or []),
            *list(second.get("attempts", []) or []),
        ]
        if not merged.get("target_device"):
            merged["target_device"] = first.get("target_device") or second.get("target_device")
        return merged

    @classmethod
    def _serialize_match(
        cls,
        device: Any,
        advertisement_data: Any | None = None,
    ) -> dict[str, Any]:
        normalized_address = cls._normalize_address(getattr(device, "address", None))
        payload: dict[str, Any] = {
            "name": device.name or "Unknown",
            "address": device.address,
            "normalized_address": normalized_address,
            "rssi": cls._extract_rssi(device, advertisement_data),
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

        raw_devices, matches, matched_targets, scan_rounds_completed, protocol_capture = (
            await self._discover_targets(BleakScanner)
        )

        candidate_devices = sorted(
            raw_devices,
            key=self._candidate_score,
            reverse=True,
        )[:5]

        if matched_targets and (protocol_capture is None or not protocol_capture.get("connected")):
            target_payload, target_device = matched_targets[0]
            fallback_protocol_capture = await self._capture_target_protocol(
                target_device,
                target_payload,
            )
            protocol_capture = self._merge_protocol_captures(
                protocol_capture,
                fallback_protocol_capture,
            )

        capture_payload = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "profile": profile.name,
            "target_names": list(self._target_names),
            "target_addresses": sorted(self._target_addresses),
            "scan_timeout_seconds": self._scan_timeout_seconds,
            "scan_rounds_configured": self._scan_rounds,
            "scan_rounds_completed": scan_rounds_completed,
            "scan_pause_seconds": self._scan_pause_seconds,
            "matched_devices": matches,
            "candidate_devices": candidate_devices,
            "protocol_capture": protocol_capture,
            "all_devices": raw_devices,
        }
        capture_path = self._write_capture(capture_payload)
        details = {
            "profile": profile.name,
            "discovered_devices": matches,
            "candidate_devices": candidate_devices,
            "capture_file": str(capture_path),
            "scan_timeout_seconds": self._scan_timeout_seconds,
            "scan_rounds_completed": scan_rounds_completed,
            "scan_rounds_configured": self._scan_rounds,
            "scan_pause_seconds": self._scan_pause_seconds,
            "target_addresses": sorted(self._target_addresses),
        }
        message = "Live Bluetooth discovery is wired up, but protocol decoding still needs a packet capture from the MiniPC target."
        if protocol_capture is not None:
            notification_capture = protocol_capture.get("notification_capture") or {}
            details["target_connection_status"] = (
                "connected" if protocol_capture.get("connected") else "failed"
            )
            details["target_service_count"] = protocol_capture.get("service_count")
            details["notification_packet_count"] = notification_capture.get("packet_count", 0)
            if protocol_capture.get("error_message"):
                details["target_connection_error"] = str(protocol_capture["error_message"])

            if protocol_capture.get("connected"):
                message = (
                    "Target scale discovered and protocol capture saved. "
                    "Live measurement decoding still needs analysis."
                )
            else:
                message = (
                    "Target scale was discovered, but the direct BLE connection did not complete. "
                    "Review the MiniPC capture for GATT details."
                )
        elif self._target_addresses:
            message = (
                "The configured target scale was not seen during the live scan window. "
                "Wake the scale and keep it active while the MiniPC is scanning."
            )
        raise ScaleAdapterError(message, details=details)


def build_scale_adapter(settings: Settings) -> ScaleAdapter:
    if settings.adapter_mode == "live":
        return LiveBleAdapter(settings)
    return ReplayAdapter(settings)
