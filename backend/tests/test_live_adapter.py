from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from app.core.config import Settings
from app.services.adapters import LiveBleAdapter


def build_settings(tmp_path: Path) -> Settings:
    repo_root = Path(__file__).resolve().parents[2]
    return Settings(
        app_name="Local Scale Test",
        env="test",
        api_prefix="/api",
        database_url=f"sqlite:///{tmp_path / 'test.sqlite3'}",
        data_root=tmp_path,
        adapter_mode="live",
        replay_fixture_path=repo_root / "fixtures" / "replay" / "sample_measurements.json",
        import_fixture_path=repo_root / "fixtures" / "imports" / "sample_import.csv",
        frontend_dist_path=repo_root / "frontend" / "dist",
        cors_origins=("http://localhost:5173",),
        session_timeout_seconds=10,
        replay_delay_seconds=0.0,
        ble_scan_timeout_seconds=1.0,
        ble_scan_rounds=1,
        ble_scan_pause_seconds=0.0,
        ble_connect_timeout_seconds=1.0,
        ble_connect_retries=3,
        ble_connect_retry_pause_seconds=0.0,
        ble_notify_capture_seconds=0.0,
        seed_demo_data=False,
        target_scale_names=("Soundlogic", "OKOK", "Chipsea"),
        target_scale_addresses=("41:06:4A:9D:15:1E",),
        ble_capture_dir=tmp_path / "ble-captures",
    )


def test_scan_once_stops_scanner_before_connecting(monkeypatch, tmp_path: Path):
    adapter = LiveBleAdapter(build_settings(tmp_path))
    device = SimpleNamespace(address="41:06:4A:9D:15:1E", name=None)
    advertisement_data = SimpleNamespace(
        local_name=None,
        manufacturer_data={21696: bytes.fromhex("1d18138808082541064a9d151e")},
        service_data={},
        service_uuids=[],
        tx_power=None,
        platform_data=[],
        rssi=-56,
    )
    observed: dict[str, object] = {}

    class FakeScanner:
        instance: "FakeScanner | None" = None

        def __init__(self, detection_callback):
            self._detection_callback = detection_callback
            self.stopped = False
            FakeScanner.instance = self

        async def start(self) -> None:
            self._detection_callback(device, advertisement_data)

        async def stop(self) -> None:
            self.stopped = True

    async def fake_capture(self, matched_device, matched_payload, **kwargs):
        observed["scanner_stopped"] = FakeScanner.instance is not None and FakeScanner.instance.stopped
        observed["matched_device"] = matched_device
        observed["matched_payload"] = matched_payload
        observed["connection_targets"] = kwargs["connection_targets"]
        observed["max_attempts"] = kwargs["max_attempts"]
        return {"attempted": True, "connected": False, "attempts": []}

    monkeypatch.setattr(LiveBleAdapter, "_capture_target_protocol", fake_capture)

    seen_devices, matched_targets, protocol_capture = asyncio.run(adapter._scan_once(FakeScanner))

    assert len(seen_devices) == 1
    assert len(matched_targets) == 1
    assert protocol_capture == {"attempted": True, "connected": False, "attempts": []}
    assert observed["scanner_stopped"] is True
    assert observed["matched_device"] is device
    assert observed["matched_payload"] == matched_targets[0][0]
    assert observed["connection_targets"] == [
        ("device", device),
        ("address", "41:06:4a:9d:15:1e"),
    ]
    assert observed["max_attempts"] == 1


def test_discover_targets_keeps_scanning_after_failed_connect(monkeypatch, tmp_path: Path):
    adapter = LiveBleAdapter(build_settings(tmp_path))
    adapter._scan_rounds = 3
    device = SimpleNamespace(address="41:06:4A:9D:15:1E", name=None)
    match_payload = {
        "address": "41:06:4A:9D:15:1E",
        "normalized_address": "41:06:4a:9d:15:1e",
        "name": "Unknown",
        "match_reasons": ["target address"],
        "rssi": -58,
    }
    rounds = [
        ([match_payload], [(match_payload, device)], {"attempted": True, "connected": False}),
        ([match_payload], [(match_payload, device)], {"attempted": True, "connected": True}),
    ]
    observed_rounds: list[int] = []

    async def fake_scan_once(self, scanner_cls):
        observed_rounds.append(len(observed_rounds) + 1)
        return rounds[len(observed_rounds) - 1]

    monkeypatch.setattr(LiveBleAdapter, "_scan_once", fake_scan_once)

    raw_devices, matches, matched_records, rounds_completed, protocol_capture = asyncio.run(
        adapter._discover_targets(object())
    )

    assert observed_rounds == [1, 2]
    assert rounds_completed == 2
    assert len(raw_devices) == 1
    assert len(matches) == 1
    assert len(matched_records) == 1
    assert protocol_capture == {"attempted": True, "connected": True}
