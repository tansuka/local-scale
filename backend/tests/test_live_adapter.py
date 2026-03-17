from __future__ import annotations

import asyncio
from datetime import datetime, timezone
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


def _chipsea_payload(weight_kg: float, normalized_address: str) -> bytes:
    raw_weight = int(round(weight_kg * 100))
    mac_bytes = bytes.fromhex(normalized_address.replace(":", ""))
    return bytes([0x10, 0x00]) + raw_weight.to_bytes(2, byteorder="little") + bytes(8) + mac_bytes


def test_scan_once_collects_target_advertisement_history(tmp_path: Path):
    adapter = LiveBleAdapter(build_settings(tmp_path))
    adapter._scan_timeout_seconds = 0.0
    target_device = SimpleNamespace(address="41:06:4A:9D:15:1E", name=None)
    target_advertisement = SimpleNamespace(
        local_name=None,
        manufacturer_data={21696: bytes.fromhex("1d18138808082541064a9d151e")},
        service_data={},
        service_uuids=[],
        tx_power=None,
        platform_data=[],
        rssi=-56,
    )
    other_device = SimpleNamespace(address="58:26:AF:72:F2:82", name=None)
    other_advertisement = SimpleNamespace(
        local_name=None,
        manufacturer_data={76: bytes.fromhex("12020001")},
        service_data={},
        service_uuids=[],
        tx_power=None,
        platform_data=[],
        rssi=-40,
    )

    class FakeScanner:
        instance: "FakeScanner | None" = None

        def __init__(self, detection_callback, **_kwargs):
            self._detection_callback = detection_callback
            self.stopped = False
            FakeScanner.instance = self

        async def start(self) -> None:
            self._detection_callback(target_device, target_advertisement)
            self._detection_callback(other_device, other_advertisement)

        async def stop(self) -> None:
            self.stopped = True

    seen_devices, matched_targets, advertisement_history = asyncio.run(adapter._scan_once(FakeScanner, 1))

    assert len(seen_devices) == 2
    assert len(matched_targets) == 1
    assert len(advertisement_history) == 1
    assert advertisement_history[0]["normalized_address"] == "41:06:4a:9d:15:1e"
    assert advertisement_history[0]["round"] == 1
    assert FakeScanner.instance is not None and FakeScanner.instance.stopped is True


def test_analyze_advertisement_history_selects_stable_chipsea_weight():
    normalized_address = "41:06:4a:9d:15:1e"
    payload = _chipsea_payload(70.25, normalized_address)
    history = [
        {
            "round": 1,
            "sequence": 1,
            "received_at": datetime(2026, 3, 17, 14, 0, tzinfo=timezone.utc).isoformat(),
            "address": "41:06:4A:9D:15:1E",
            "normalized_address": normalized_address,
            "manufacturer_data": {str(0xFFF0): payload.hex()},
            "match_reasons": ["target address"],
        },
        {
            "round": 1,
            "sequence": 2,
            "received_at": datetime(2026, 3, 17, 14, 0, 1, tzinfo=timezone.utc).isoformat(),
            "address": "41:06:4A:9D:15:1E",
            "normalized_address": normalized_address,
            "manufacturer_data": {str(0xFFF0): payload.hex()},
            "match_reasons": ["target address"],
        },
    ]

    analysis = LiveBleAdapter._analyze_advertisement_history(history)

    assert analysis["parsed_candidate_count"] == 2
    assert analysis["selected_candidate"] is not None
    assert analysis["selected_candidate"]["weight_kg"] == 70.25
    assert analysis["selected_candidate"]["count"] == 2


def test_analyze_advertisement_history_selects_single_compact_candidate():
    normalized_address = "41:06:4a:9d:15:1e"
    history = [
        {
            "round": 2,
            "sequence": 1,
            "received_at": datetime(2026, 3, 17, 15, 23, 32, tzinfo=timezone.utc).isoformat(),
            "address": "41:06:4A:9D:15:1E",
            "normalized_address": normalized_address,
            "manufacturer_data": {"23744": "1cfb138808082541064a9d151e"},
            "match_reasons": ["target address"],
        }
    ]

    analysis = LiveBleAdapter._analyze_advertisement_history(history)

    assert analysis["parsed_candidate_count"] == 1
    assert analysis["selected_candidate"] is not None
    assert analysis["selected_candidate"]["parser"] == "chipsea_compact_adv_v1"
    assert analysis["selected_candidate"]["weight_kg"] == 74.19
    assert analysis["selected_candidate"]["impedance_ohm"] == 500
    assert analysis["selected_candidate"]["samples"][0]["impedance_ohm"] == 500


def test_measurement_from_advertisement_candidate_keeps_impedance():
    candidate = {
        "parser": "chipsea_compact_adv_v1",
        "weight_kg": 74.19,
        "impedance_ohm": 500,
        "count": 1,
        "latest_received_at": datetime(2026, 3, 17, 15, 23, 32, tzinfo=timezone.utc).isoformat(),
        "samples": [
            {
                "parser": "chipsea_compact_adv_v1",
                "weight_kg": 74.19,
                "impedance_ohm": 500,
            }
        ],
    }

    measurement = LiveBleAdapter._measurement_from_advertisement_candidate(candidate)

    assert measurement["raw_payload_json"]["impedance_ohm"] == 500
    assert measurement["raw_payload_json"]["samples"][0]["impedance_ohm"] == 500


def test_discover_targets_merges_target_history(monkeypatch, tmp_path: Path):
    adapter = LiveBleAdapter(build_settings(tmp_path))
    adapter._scan_rounds = 4
    device = SimpleNamespace(address="41:06:4A:9D:15:1E", name=None)
    match_payload = {
        "address": "41:06:4A:9D:15:1E",
        "normalized_address": "41:06:4a:9d:15:1e",
        "name": "Unknown",
        "match_reasons": ["target address"],
        "rssi": -58,
    }
    compact_history_entry_round_1 = {
        "address": "41:06:4A:9D:15:1E",
        "normalized_address": "41:06:4a:9d:15:1e",
        "manufacturer_data": {"24256": "1cfb138808082541064a9d151e"},
        "service_data": {},
        "service_uuids": [],
        "round": 1,
        "sequence": 1,
        "received_at": datetime(2026, 3, 17, 15, 43, 36, tzinfo=timezone.utc).isoformat(),
    }
    compact_history_entry_round_2 = {
        "address": "41:06:4A:9D:15:1E",
        "normalized_address": "41:06:4a:9d:15:1e",
        "manufacturer_data": {"24256": "1cfb138808082541064a9d151e"},
        "service_data": {},
        "service_uuids": [],
        "round": 2,
        "sequence": 1,
        "received_at": datetime(2026, 3, 17, 15, 43, 46, tzinfo=timezone.utc).isoformat(),
    }
    rounds = [
        (
            [match_payload],
            [(match_payload, device)],
            [compact_history_entry_round_1],
        ),
        (
            [match_payload],
            [(match_payload, device)],
            [compact_history_entry_round_2],
        ),
    ]
    observed_rounds: list[int] = []

    async def fake_scan_once(self, scanner_cls, round_number):
        observed_rounds.append(round_number)
        return rounds[round_number - 1]

    monkeypatch.setattr(LiveBleAdapter, "_scan_once", fake_scan_once)

    raw_devices, matches, matched_records, rounds_completed, advertisement_history = asyncio.run(
        adapter._discover_targets(object())
    )

    assert observed_rounds == [1, 2]
    assert rounds_completed == 2
    assert len(raw_devices) == 1
    assert len(matches) == 1
    assert len(matched_records) == 1
    assert [item["round"] for item in advertisement_history] == [1, 2]
    assert adapter._has_two_matching_target_packets(advertisement_history) is True
