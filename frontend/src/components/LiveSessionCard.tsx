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

export function LiveSessionCard({
  session,
  selectedProfile,
  loading,
  onStart,
  details,
}: LiveSessionCardProps) {
  const copy = session ? STATUS_COPY[session.status] ?? session.status : "No active weigh session.";
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
        <div className={`status-pill ${session?.status ?? "idle"}`}>{session?.status ?? "idle"}</div>
        <p className="muted compact-copy">{copy}</p>
        {session?.error_message ? (
          <div className="alert-card">
            <strong>Live capture note</strong>
            <p>{session.error_message}</p>
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
