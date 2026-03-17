# MiniPC Deployment Notes

## Guest Choice

- Prefer a **Debian VM** if you want to keep the MiniPC's integrated Bluetooth adapter.
- Prefer a **Debian LXC** only when you can pass through a dedicated USB Bluetooth dongle cleanly.

## Host Preparation

1. Create the guest and assign a persistent volume for `/var/lib/local-scale`.
2. Install Python 3.12+, BlueZ, and build essentials.
3. Create a service account:

```bash
sudo useradd --system --home /opt/local-scale --shell /usr/sbin/nologin localscale
```

## App Deployment

1. Copy the repo to `/opt/local-scale`.
2. Build the frontend on the target or build locally and copy `frontend/dist`.
3. Create the backend venv and install the package:

```bash
cd /opt/local-scale/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

4. Copy [deploy/local-scale.env.example](/Users/tansukahyaoglu/Development/local-scale/deploy/local-scale.env.example) to `/etc/local-scale/local-scale.env` and adjust paths.
5. Install [deploy/local-scale.service](/Users/tansukahyaoglu/Development/local-scale/deploy/local-scale.service) to `/etc/systemd/system/local-scale.service`.
6. Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now local-scale
```

## Bluetooth Reality Check

The live adapter can already discover likely OKOK-compatible devices, but it still needs a real packet capture from the MiniPC to finish the Soundlogic/OKOK decoder. Each live scan now writes a JSON capture under `LOCAL_SCALE_BLE_CAPTURE_DIR` or, by default, `<LOCAL_SCALE_DATA_DIR>/ble-captures/`.

If OKOK shows a specific BLE MAC, set it in `LOCAL_SCALE_TARGET_ADDRESSES` so the scanner can highlight exact address matches even when the device name is hidden. You can also widen the scan window with `LOCAL_SCALE_BLE_SCAN_TIMEOUT_SECONDS` when the scale only advertises briefly after you step on it.
