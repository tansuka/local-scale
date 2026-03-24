import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";

import {
  cancelSession,
  createProfile,
  commitImport,
  deleteMeasurement,
  fetchCharts,
  fetchCurrentSession,
  fetchDashboard,
  previewImport,
  reassignMeasurement,
  startSession,
  updateMeasurement,
  updateProfile,
} from "./lib/api";
import type {
  ChartResponse,
  DashboardPayload,
  HealthAnalysis,
  LiveEvent,
  Measurement,
  Profile,
  WeighSession,
} from "./lib/types";
import { AdminPanel } from "./components/AdminPanel";
import { ImportPanel } from "./components/ImportPanel";
import { LiveSessionCard } from "./components/LiveSessionCard";
import { MetricPanel } from "./components/MetricPanel";
import { ProfileForm } from "./components/ProfileForm";
import { ProfileHealthSummary } from "./components/ProfileHealthSummary";
import { ProfileSwitcher } from "./components/ProfileSwitcher";
import { TrendsPanel } from "./components/TrendsPanel";
import { formatDateTime } from "./lib/dates";

const STORAGE_KEY = "local-scale:selected-profile-id";
const THEME_STORAGE_KEY = "local-scale:theme";
type TabKey = "overview" | "trends" | "profile" | "admin";
type ThemeMode = "light" | "dark";

function readSelectedProfileId(): number | null {
  const rawValue = window.localStorage.getItem(STORAGE_KEY);
  if (!rawValue) {
    return null;
  }
  const parsed = Number(rawValue);
  return Number.isFinite(parsed) ? parsed : null;
}

function writeSelectedProfileId(profileId: number) {
  window.localStorage.setItem(STORAGE_KEY, String(profileId));
  const url = new URL(window.location.href);
  url.searchParams.set("profile", String(profileId));
  window.history.replaceState({}, "", url);
}

function readTheme(): ThemeMode {
  const rawValue = window.localStorage.getItem(THEME_STORAGE_KEY);
  return rawValue === "dark" ? "dark" : "light";
}

function selectedProfileFromQuery(): number | null {
  const params = new URLSearchParams(window.location.search);
  const value = params.get("profile");
  if (!value) {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function ThemeIcon({ theme }: { theme: ThemeMode }) {
  if (theme === "light") {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <path
          d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"
          fill="none"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.8"
        />
      </svg>
    );
  }

  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="4.1" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M12 2.5v2.2M12 19.3v2.2M21.5 12h-2.2M4.7 12H2.5M18.7 5.3l-1.6 1.6M6.9 17.1l-1.6 1.6M18.7 18.7l-1.6-1.6M6.9 6.9 5.3 5.3"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="1.8"
      />
    </svg>
  );
}

function UserIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path
        d="M12 12a4 4 0 1 0-4-4 4 4 0 0 0 4 4Zm0 2.2c-4.1 0-7.4 2.3-7.4 5.2v.1h14.8v-.1c0-2.9-3.3-5.2-7.4-5.2Z"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
    </svg>
  );
}

export function App() {
  const [activeTab, setActiveTab] = useState<TabKey>("overview");
  const [theme, setTheme] = useState<ThemeMode>(readTheme);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState<number | null>(
    selectedProfileFromQuery() ?? readSelectedProfileId(),
  );
  const [measurements, setMeasurements] = useState<Measurement[]>([]);
  const [charts, setCharts] = useState<ChartResponse | null>(null);
  const [healthAnalysis, setHealthAnalysis] = useState<HealthAnalysis | null>(null);
  const [currentSession, setCurrentSession] = useState<WeighSession | null>(null);
  const [liveDetails, setLiveDetails] = useState<Record<string, unknown> | null>(null);
  const [loadingStart, setLoadingStart] = useState(false);
  const [loadingCancel, setLoadingCancel] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const websocketRef = useRef<WebSocket | null>(null);
  const userMenuRef = useRef<HTMLDivElement | null>(null);

  const selectedProfile = useMemo(
    () => profiles.find((profile) => profile.id === selectedProfileId) ?? null,
    [profiles, selectedProfileId],
  );

  const hydrateDashboard = async (profileId?: number | null) => {
    const payload: DashboardPayload = await fetchDashboard(profileId);
    setProfiles(payload.profiles);
    const nextSelected =
      profileId ?? payload.selected_profile_id ?? payload.profiles[0]?.id ?? null;
    if (nextSelected !== null) {
      setSelectedProfileId(nextSelected);
      writeSelectedProfileId(nextSelected);
    }
    setMeasurements(payload.measurements);
    setCharts(payload.charts ?? null);
    setHealthAnalysis(payload.health_analysis ?? null);
  };

  useEffect(() => {
    void hydrateDashboard(selectedProfileId).catch((caughtError: Error) =>
      setError(caughtError.message),
    );
    void fetchCurrentSession()
      .then(setCurrentSession)
      .catch((caughtError: Error) => setError(caughtError.message));
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  useEffect(() => {
    if (!userMenuOpen) {
      return undefined;
    }

    const handlePointerDown = (event: MouseEvent) => {
      if (
        userMenuRef.current &&
        event.target instanceof Node &&
        !userMenuRef.current.contains(event.target)
      ) {
        setUserMenuOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setUserMenuOpen(false);
      }
    };

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [userMenuOpen]);

  useEffect(() => {
    if (selectedProfileId === null) {
      return;
    }
    void hydrateDashboard(selectedProfileId).catch((caughtError: Error) =>
      setError(caughtError.message),
    );
  }, [selectedProfileId]);

  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const websocket = new WebSocket(`${protocol}://${window.location.host}/api/ws/live`);
    websocketRef.current = websocket;
    const keepalive = window.setInterval(() => {
      if (websocket.readyState === WebSocket.OPEN) {
        websocket.send("ping");
      }
    }, 25000);

    websocket.onmessage = (event) => {
      const payload = JSON.parse(event.data) as LiveEvent;
      if (payload.type === "session.updated") {
        setCurrentSession(payload.session);
        setLiveDetails(payload.details ?? null);
      }
      if (
        payload.type === "measurement.created" &&
        payload.measurement.profile_id === selectedProfileId
      ) {
        setMeasurements((current) => [payload.measurement, ...current].slice(0, 365));
        void fetchCharts(payload.measurement.profile_id).then(setCharts);
        void hydrateDashboard(payload.measurement.profile_id).catch((caughtError: Error) =>
          setError(caughtError.message),
        );
      }
    };

    return () => {
      window.clearInterval(keepalive);
      websocket.close();
    };
  }, [selectedProfileId]);

  const latestMeasurement = measurements[0] ?? null;
  const pendingCount = measurements.filter(
    (measurement) => measurement.assignment_state !== "confirmed",
  ).length;
  const sessionIsActive =
    currentSession?.status === "armed" || currentSession?.status === "capturing";

  const tabItems: Array<{ key: TabKey; label: string }> = [
    { key: "overview", label: "Overview" },
    { key: "trends", label: "Trends" },
  ];

  return (
    <div
      className="app-shell"
      style={{ "--profile-accent": selectedProfile?.color ?? "#0f766e" } as CSSProperties}
    >
      <main className="page">
        <header className="shell-header panel">
          <div className="shell-intro">
            <h1>Local Scale</h1>
          </div>
          <div className="shell-controls">
            <button
              aria-label={`Switch to ${theme === "light" ? "dark" : "light"} mode`}
              aria-pressed={theme === "dark"}
              className="theme-toggle ghost-button icon-button"
              onClick={() =>
                setTheme((currentTheme) => (currentTheme === "light" ? "dark" : "light"))
              }
              type="button"
            >
              <ThemeIcon theme={theme} />
            </button>
            <div className="user-menu" ref={userMenuRef}>
              <button
                aria-expanded={userMenuOpen}
                aria-haspopup="menu"
                aria-label="Open user menu"
                className="ghost-button icon-button user-menu-trigger"
                onClick={() => setUserMenuOpen((current) => !current)}
                type="button"
              >
                <UserIcon />
              </button>
              {userMenuOpen ? (
                <div className="user-menu-popover" role="menu">
                  <div className="user-menu-header">
                    <p className="eyebrow">Current User</p>
                    <strong>{selectedProfile?.name ?? "No user selected"}</strong>
                  </div>
                  <div className="user-menu-actions">
                    <button
                      className={`user-menu-action ${activeTab === "profile" ? "active" : ""}`}
                      onClick={() => {
                        setActiveTab("profile");
                        setUserMenuOpen(false);
                      }}
                      type="button"
                    >
                      Profile
                    </button>
                    <button
                      className={`user-menu-action ${activeTab === "admin" ? "active" : ""}`}
                      onClick={() => {
                        setActiveTab("admin");
                        setUserMenuOpen(false);
                      }}
                      type="button"
                    >
                      Admin Panel
                    </button>
                  </div>
                  <div className="user-menu-section">
                    <ProfileSwitcher
                      label="Switch user"
                      profiles={profiles}
                      selectedProfileId={selectedProfileId}
                      stacked
                      onSelect={(profileId) => {
                        setSelectedProfileId(profileId);
                        writeSelectedProfileId(profileId);
                        setUserMenuOpen(false);
                      }}
                    />
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </header>
        {error ? <div className="error-banner">{error}</div> : null}
        <section className="tab-shell">
          <div className="tab-row">
            {tabItems.map((tab) => (
              <button
                key={tab.key}
                className={`tab-button ${activeTab === tab.key ? "active" : ""}`}
                onClick={() => setActiveTab(tab.key)}
                type="button"
              >
                {tab.label}
              </button>
            ))}
          </div>

          {activeTab === "overview" ? (
            <div className="tab-content">
              <div className="overview-grid">
                <section className="panel profile-summary-card profile-summary-hero">
                  <p className="eyebrow">Selected Profile</p>
                  <h2>{selectedProfile?.name ?? "No profile selected"}</h2>
                  <ProfileHealthSummary
                    analysis={healthAnalysis}
                    pendingCount={pendingCount}
                    profile={selectedProfile}
                  />
                  <div className="summary-strip">
                    <div>
                      <span>Last weight</span>
                      <strong>
                        {latestMeasurement ? `${latestMeasurement.weight_kg} kg` : "—"}
                      </strong>
                      <small className="summary-meta">
                        {latestMeasurement
                          ? `Updated ${formatDateTime(latestMeasurement.measured_at)}`
                          : "No measurement yet"}
                      </small>
                    </div>
                  </div>
                </section>
                <LiveSessionCard
                  cancelling={loadingCancel}
                  details={liveDetails}
                  loading={loadingStart}
                  onCancel={async () => {
                    if (!currentSession || !sessionIsActive) {
                      return;
                    }
                    setLoadingCancel(true);
                    setError(null);
                    try {
                      const session = await cancelSession(currentSession.id);
                      setCurrentSession(session);
                      setLiveDetails(null);
                    } catch (caughtError) {
                      setError((caughtError as Error).message);
                    } finally {
                      setLoadingCancel(false);
                    }
                  }}
                  onStart={async () => {
                    if (!selectedProfileId || sessionIsActive) {
                      return;
                    }
                    setLoadingStart(true);
                    setError(null);
                    try {
                      const session = await startSession(selectedProfileId);
                      setCurrentSession(session);
                      setLiveDetails(null);
                    } catch (caughtError) {
                      setError((caughtError as Error).message);
                    } finally {
                      setLoadingStart(false);
                    }
                  }}
                  selectedProfile={selectedProfile ?? undefined}
                  session={currentSession}
                />
              </div>
              <MetricPanel measurement={latestMeasurement} profile={selectedProfile} />
            </div>
          ) : null}

          {activeTab === "trends" ? (
            <TrendsPanel
              charts={charts}
              measurements={measurements}
              profiles={profiles}
              selectedProfileId={selectedProfileId}
              theme={theme}
              onUpdateMeasurement={async (measurementId, payload) => {
                const updated = await updateMeasurement(measurementId, payload);
                setMeasurements((current) =>
                  current.map((measurement) =>
                    measurement.id === updated.id ? updated : measurement,
                  ),
                );
                if (selectedProfileId === updated.profile_id) {
                  const nextCharts = await fetchCharts(updated.profile_id);
                  setCharts(nextCharts);
                }
              }}
              onDelete={async (measurementId) => {
                await deleteMeasurement(measurementId);
                await hydrateDashboard(selectedProfileId);
              }}
              onReassign={async (measurementId, profileId) => {
                await reassignMeasurement(measurementId, profileId);
                await hydrateDashboard(selectedProfileId);
              }}
            />
          ) : null}

          {activeTab === "profile" ? (
            <div className="tab-content">
              <div className="settings-grid">
                <ProfileForm
                  selectedProfile={selectedProfile}
                  onCreate={createProfile}
                  onUpdate={updateProfile}
                  onSaved={async (profile) => {
                    setSelectedProfileId(profile.id);
                    writeSelectedProfileId(profile.id);
                    await hydrateDashboard(profile.id);
                  }}
                />
                <ImportPanel
                  selectedProfile={selectedProfile ?? undefined}
                  onPreview={previewImport}
                  onCommit={(file) =>
                    commitImport(file, selectedProfileId ?? undefined).then(async (result) => {
                      await hydrateDashboard(selectedProfileId);
                      return result;
                    })
                  }
                />
              </div>
            </div>
          ) : null}

          {activeTab === "admin" ? (
            <div className="tab-content">
              <AdminPanel
                selectedProfile={selectedProfile}
                onAnalysisUpdated={(analysis) => setHealthAnalysis(analysis)}
              />
            </div>
          ) : null}
        </section>
      </main>
    </div>
  );
}
