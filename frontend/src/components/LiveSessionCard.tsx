import { useEffect, useState } from "react";

import type { Profile, WeighSession } from "../lib/types";

type LiveSessionCardProps = {
  session: WeighSession | null;
  selectedProfile?: Profile;
  loading: boolean;
  cancelling: boolean;
  onStart: () => void;
  onCancel: () => void;
  details?: Record<string, unknown> | null;
};

const STATUS_COPY: Record<string, string> = {
  armed: "Session armed. Step on the scale when you are ready.",
  capturing: "Listening for the scale now.",
  completed: "Measurement captured.",
  failed: "The session did not complete.",
  cancelled: "Weigh-in cancelled.",
};

function isActiveSession(session: WeighSession | null): boolean {
  return session?.status === "armed" || session?.status === "capturing";
}

function formatRemainingTime(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function isDecoderPendingMessage(message?: string | null): boolean {
  return !!message?.toLowerCase().includes("protocol decoding still needs a packet capture");
}

function isProtocolCaptureMessage(message?: string | null): boolean {
  const lowered = message?.toLowerCase() ?? "";
  return (
    lowered.includes("protocol capture saved") ||
    lowered.includes("direct ble connection did not complete")
  );
}

function isTargetNotSeenMessage(message?: string | null): boolean {
  return !!message?.toLowerCase().includes("configured target scale was not seen");
}

function displayStatus(session: WeighSession | null): string {
  if (isTargetNotSeenMessage(session?.error_message) && session?.status === "failed") {
    return "target not seen";
  }
  if (isProtocolCaptureMessage(session?.error_message) && session?.status === "failed") {
    return "protocol capture";
  }
  if (isDecoderPendingMessage(session?.error_message) && session?.status === "failed") {
    return "discovery ready";
  }
  return session?.status ?? "idle";
}

function displayStatusTone(session: WeighSession | null): string {
  if (session?.status === "cancelled") {
    return "info";
  }
  if (isTargetNotSeenMessage(session?.error_message) && session?.status === "failed") {
    return "info";
  }
  if (isProtocolCaptureMessage(session?.error_message) && session?.status === "failed") {
    return "info";
  }
  if (isDecoderPendingMessage(session?.error_message) && session?.status === "failed") {
    return "info";
  }
  return session?.status ?? "idle";
}

function statusCopy(session: WeighSession | null): string {
  if (isTargetNotSeenMessage(session?.error_message) && session?.status === "failed") {
    return "The configured scale was not seen during the repeated scan window.";
  }
  if (isProtocolCaptureMessage(session?.error_message) && session?.status === "failed") {
    return "The scale was found and a protocol capture was saved for analysis.";
  }
  if (isDecoderPendingMessage(session?.error_message) && session?.status === "failed") {
    return "Bluetooth discovery is working. Packet decoding on the MiniPC target is still pending.";
  }
  return session ? STATUS_COPY[session.status] ?? session.status : "No active weigh session.";
}

function liveErrorTitle(message?: string | null): string {
  if (!message) {
    return "Live capture note";
  }
  const lowered = message.toLowerCase();
  if (lowered.includes("protocol capture saved")) {
    return "Protocol capture saved";
  }
  if (lowered.includes("direct ble connection did not complete")) {
    return "Scale connection incomplete";
  }
  if (lowered.includes("configured target scale was not seen")) {
    return "Scale not seen yet";
  }
  if (lowered.includes("weigh-in cancelled")) {
    return "Weigh-in cancelled";
  }
  if (lowered.includes("protocol decoding still needs a packet capture")) {
    return "Decoder setup still needed";
  }
  if (lowered.includes("no bluetooth adapter")) {
    return "Bluetooth adapter not available";
  }
  if (lowered.includes("bluetooth is not available")) {
    return "Bluetooth is unavailable";
  }
  return "Live capture note";
}

export function LiveSessionCard({
  session,
  selectedProfile,
  loading,
  cancelling,
  onStart,
  onCancel,
  details,
}: LiveSessionCardProps) {
  const [now, setNow] = useState(() => Date.now());
  const copy = statusCopy(session);
  const shownStatus = displayStatus(session);
  const shownStatusTone = displayStatusTone(session);
  const sessionIsActive = isActiveSession(session);
  const captureFile = typeof details?.capture_file === "string" ? details.capture_file : null;
  const scanTimeoutSeconds =
    typeof details?.scan_timeout_seconds === "number" ? details.scan_timeout_seconds : null;
  const scanRoundsCompleted =
    typeof details?.scan_rounds_completed === "number" ? details.scan_rounds_completed : null;
  const scanRoundsConfigured =
    typeof details?.scan_rounds_configured === "number" ? details.scan_rounds_configured : null;
  const targetConnectionStatus =
    typeof details?.target_connection_status === "string" ? details.target_connection_status : null;
  const targetServiceCount =
    typeof details?.target_service_count === "number" ? details.target_service_count : null;
  const notificationPacketCount =
    typeof details?.notification_packet_count === "number"
      ? details.notification_packet_count
      : null;
  const targetConnectionError =
    typeof details?.target_connection_error === "string" ? details.target_connection_error : null;
  const targetAddresses = Array.isArray(details?.target_addresses)
    ? (details?.target_addresses as string[])
    : [];
  const discoveredDevices = Array.isArray(details?.discovered_devices)
    ? (details?.discovered_devices as Array<{
        name?: string;
        address?: string;
        rssi?: number | null;
        match_reasons?: string[];
      }>)
    : [];
  const candidateDevices = Array.isArray(details?.candidate_devices)
    ? (details?.candidate_devices as Array<{
        name?: string;
        address?: string;
        rssi?: number | null;
        match_reasons?: string[];
      }>)
    : [];
  const expiresAt = session?.expires_at ? Date.parse(session.expires_at) : NaN;
  const remainingSeconds =
    sessionIsActive && Number.isFinite(expiresAt)
      ? Math.max(0, Math.ceil((expiresAt - now) / 1000))
      : null;

  useEffect(() => {
    if (!sessionIsActive) {
      return;
    }
    setNow(Date.now());
    const timer = window.setInterval(() => {
      setNow(Date.now());
    }, 1000);
    return () => window.clearInterval(timer);
  }, [sessionIsActive, session?.expires_at]);

  return (
    <section className="panel live-panel">
      <div className="live-actions">
        <p className="eyebrow">Live Weigh-In</p>
        <div className="live-action-row">
          <button
            className="primary-button big-weigh-button"
            disabled={loading || cancelling || !selectedProfile || sessionIsActive}
            onClick={onStart}
            type="button"
          >
            {loading ? "Starting..." : sessionIsActive ? "Weigh-In Running" : "Start Weigh-In"}
          </button>
          {sessionIsActive ? (
            <button
              className="ghost-button danger-button"
              disabled={loading || cancelling}
              onClick={onCancel}
              type="button"
            >
              {cancelling ? "Cancelling..." : "Cancel"}
            </button>
          ) : null}
        </div>
        <div className={`status-pill ${shownStatusTone}`}>{shownStatus}</div>
        <p className="muted compact-copy">{copy}</p>
        {remainingSeconds !== null ? (
          <div className="live-timer">
            <strong>Time remaining: {formatRemainingTime(remainingSeconds)}</strong>
            <span>Scan ends automatically when the timer runs out.</span>
          </div>
        ) : null}
        {session?.error_message ? (
          <div className="alert-card">
            <strong>{liveErrorTitle(session.error_message)}</strong>
            <p>{session.error_message}</p>
            {captureFile ? <p>Capture saved to {captureFile}</p> : null}
            {scanTimeoutSeconds ? <p>Scan window: {scanTimeoutSeconds} seconds</p> : null}
            {scanRoundsCompleted !== null && scanRoundsConfigured !== null ? (
              <p>
                Scan rounds: {scanRoundsCompleted} / {scanRoundsConfigured}
              </p>
            ) : null}
            {targetAddresses.length > 0 ? <p>Target address: {targetAddresses.join(", ")}</p> : null}
            {targetConnectionStatus ? <p>Target connection: {targetConnectionStatus}</p> : null}
            {targetServiceCount !== null ? <p>GATT services discovered: {targetServiceCount}</p> : null}
            {notificationPacketCount !== null ? (
              <p>Notification packets captured: {notificationPacketCount}</p>
            ) : null}
            {targetConnectionError ? <p>Connection note: {targetConnectionError}</p> : null}
            {discoveredDevices.length > 0 ? (
              <>
                <p>Matched devices</p>
                <ul className="device-list">
                  {discoveredDevices.map((device) => (
                    <li key={`${device.address}-${device.name}`}>
                      {device.name} <span>{device.address}</span>
                      {typeof device.rssi === "number" ? <span>RSSI {device.rssi}</span> : null}
                      {device.match_reasons?.length ? (
                        <span>{device.match_reasons.join(", ")}</span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
            {!discoveredDevices.length && candidateDevices.length > 0 ? (
              <>
                <p>Closest candidates from this scan</p>
                <ul className="device-list">
                  {candidateDevices.map((device) => (
                    <li key={`${device.address}-${device.name}`}>
                      {device.name} <span>{device.address}</span>
                      {typeof device.rssi === "number" ? <span>RSSI {device.rssi}</span> : null}
                      {device.match_reasons?.length ? (
                        <span>{device.match_reasons.join(", ")}</span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
          </div>
        ) : null}
      </div>
    </section>
  );
}
