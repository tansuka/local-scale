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

function displayStatus(session: WeighSession | null): string {
  if (isDecoderPendingMessage(session?.error_message) && session?.status === "failed") {
    return "discovery ready";
  }
  return session?.status ?? "idle";
}

function displayStatusTone(session: WeighSession | null): string {
  if (isDecoderPendingMessage(session?.error_message) && session?.status === "failed") {
    return "info";
  }
  return session?.status ?? "idle";
}

function statusCopy(session: WeighSession | null): string {
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
  const discoveredDevices = Array.isArray(details?.discovered_devices)
    ? (details?.discovered_devices as Array<{ name?: string; address?: string }>)
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
            {discoveredDevices.length > 0 ? (
              <ul className="device-list">
                {discoveredDevices.map((device) => (
                  <li key={`${device.address}-${device.name}`}>
                    {device.name} <span>{device.address}</span>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
      </div>
    </section>
  );
}
