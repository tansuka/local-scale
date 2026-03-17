import type { Profile, WeighSession } from "../lib/types";

type LiveSessionCardProps = {
  session: WeighSession | null;
  selectedProfile?: Profile;
  loading: boolean;
  onStart: () => void;
  details?: Record<string, unknown> | null;
};

const STATUS_COPY: Record<string, string> = {
  armed: "Session armed. Step on the scale when you are ready.",
  capturing: "Listening for the scale now.",
  completed: "Measurement captured.",
  failed: "The session did not complete.",
};

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

function displayStatus(session: WeighSession | null): string {
  if (isProtocolCaptureMessage(session?.error_message) && session?.status === "failed") {
    return "protocol capture";
  }
  if (isDecoderPendingMessage(session?.error_message) && session?.status === "failed") {
    return "discovery ready";
  }
  return session?.status ?? "idle";
}

function displayStatusTone(session: WeighSession | null): string {
  if (isProtocolCaptureMessage(session?.error_message) && session?.status === "failed") {
    return "info";
  }
  if (isDecoderPendingMessage(session?.error_message) && session?.status === "failed") {
    return "info";
  }
  return session?.status ?? "idle";
}

function statusCopy(session: WeighSession | null): string {
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
  onStart,
  details,
}: LiveSessionCardProps) {
  const copy = statusCopy(session);
  const shownStatus = displayStatus(session);
  const shownStatusTone = displayStatusTone(session);
  const captureFile = typeof details?.capture_file === "string" ? details.capture_file : null;
  const scanTimeoutSeconds =
    typeof details?.scan_timeout_seconds === "number" ? details.scan_timeout_seconds : null;
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

  return (
    <section className="panel live-panel">
      <div className="live-actions">
        <p className="eyebrow">Live Weigh-In</p>
        <button
          className="primary-button big-weigh-button"
          disabled={loading || !selectedProfile}
          onClick={onStart}
          type="button"
        >
          {loading ? "Starting..." : "Start Weigh-In"}
        </button>
        <div className={`status-pill ${shownStatusTone}`}>{shownStatus}</div>
        <p className="muted compact-copy">{copy}</p>
        {session?.error_message ? (
          <div className="alert-card">
            <strong>{liveErrorTitle(session.error_message)}</strong>
            <p>{session.error_message}</p>
            {captureFile ? <p>Capture saved to {captureFile}</p> : null}
            {scanTimeoutSeconds ? <p>Scan window: {scanTimeoutSeconds} seconds</p> : null}
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
