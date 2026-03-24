import { useEffect, useState } from "react";

import { fetchLlmSettings, runHealthAnalysis, updateLlmSettings } from "../lib/api";
import type { HealthAnalysis, LlmSettings, Profile } from "../lib/types";

type AdminPanelProps = {
  selectedProfile?: Profile | null;
  onAnalysisUpdated: (analysis: HealthAnalysis) => void;
};

type DraftState = {
  baseUrl: string;
  model: string;
  apiKey: string;
  clearStoredKey: boolean;
};

const EMPTY_DRAFT: DraftState = {
  baseUrl: "",
  model: "",
  apiKey: "",
  clearStoredKey: false,
};

function draftFromSettings(settings: LlmSettings | null): DraftState {
  if (!settings) {
    return EMPTY_DRAFT;
  }
  return {
    baseUrl: settings.base_url,
    model: settings.model,
    apiKey: "",
    clearStoredKey: false,
  };
}

export function AdminPanel({ selectedProfile, onAnalysisUpdated }: AdminPanelProps) {
  const [settings, setSettings] = useState<LlmSettings | null>(null);
  const [draft, setDraft] = useState<DraftState>(EMPTY_DRAFT);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    void fetchLlmSettings()
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setSettings(payload);
        setDraft(draftFromSettings(payload));
      })
      .catch((caughtError: Error) => {
        if (!cancelled) {
          setError(caughtError.message);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const saveSettings = async () => {
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      const payload = await updateLlmSettings({
        base_url: draft.baseUrl.trim(),
        model: draft.model.trim(),
        api_key: draft.apiKey.trim() || undefined,
        clear_api_key: draft.clearStoredKey,
      });
      setSettings(payload);
      setDraft(draftFromSettings(payload));
      setMessage("LLM settings saved.");
    } catch (caughtError) {
      setError((caughtError as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const triggerAnalysis = async () => {
    if (!selectedProfile) {
      return;
    }
    setRunning(true);
    setMessage(null);
    setError(null);
    try {
      const analysis = await runHealthAnalysis(selectedProfile.id);
      onAnalysisUpdated(analysis);
      setMessage(
        analysis.status === "ready"
          ? `Analysis refreshed for ${selectedProfile.name}.`
          : "Analysis could not be refreshed.",
      );
    } catch (caughtError) {
      setError((caughtError as Error).message);
    } finally {
      setRunning(false);
    }
  };

  return (
    <section className="panel admin-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Admin Panel</p>
          <h2>Application-wide configuration</h2>
        </div>
      </div>
      <p className="muted admin-copy">
        Configure the OpenAI-compatible endpoint used for profile health analysis and manually rerun the summary for the selected profile when you want to validate changes.
      </p>
      {loading ? <div className="import-summary">Loading admin settings...</div> : null}
      {error ? <div className="error-banner">{error}</div> : null}
      {!loading ? (
        <>
          <div className="admin-grid">
            <article className="admin-card">
              <h3>LLM Connection</h3>
              <div className="admin-form-grid">
                <label>
                  <span>Base URL</span>
                  <input
                    value={draft.baseUrl}
                    onChange={(event) =>
                      setDraft((current) => ({ ...current, baseUrl: event.target.value }))
                    }
                    placeholder="http://localhost:11434/v1"
                  />
                </label>
                <label>
                  <span>Model</span>
                  <input
                    value={draft.model}
                    onChange={(event) =>
                      setDraft((current) => ({ ...current, model: event.target.value }))
                    }
                    placeholder="gpt-4.1-mini"
                  />
                </label>
                <label className="admin-form-full">
                  <span>API key (optional)</span>
                  <input
                    type="password"
                    value={draft.apiKey}
                    onChange={(event) =>
                      setDraft((current) => ({
                        ...current,
                        apiKey: event.target.value,
                        clearStoredKey: false,
                      }))
                    }
                    placeholder={settings?.api_key_preview ?? "Leave blank to keep the current key"}
                  />
                </label>
              </div>
              <div className="admin-actions">
                <button
                  className="ghost-button"
                  type="button"
                  onClick={() => {
                    setDraft((current) => ({ ...current, apiKey: "", clearStoredKey: true }));
                    setMessage("The saved API key will be removed the next time you save.");
                  }}
                >
                  Remove Saved Key
                </button>
                <button className="primary-button" disabled={saving} type="button" onClick={saveSettings}>
                  {saving ? "Saving..." : "Save LLM Settings"}
                </button>
              </div>
              <p className="analysis-note muted">
                {settings?.has_api_key
                  ? `Saved key on file: ${settings.api_key_preview}`
                  : "No API key stored."}
              </p>
            </article>
            <article className="admin-card">
              <h3>Prompt and Analysis</h3>
              <div className="admin-detail-list">
                <div className="admin-detail-row">
                  <span>Prompt path</span>
                  <strong>{settings?.prompt_path ?? "—"}</strong>
                </div>
                <div className="admin-detail-row">
                  <span>Prompt status</span>
                  <strong>{settings?.prompt_loaded ? "Loaded on startup" : "Not loaded"}</strong>
                </div>
                {settings?.prompt_error ? (
                  <p className="analysis-note muted">{settings.prompt_error}</p>
                ) : null}
                <div className="admin-detail-row">
                  <span>Selected profile</span>
                  <strong>{selectedProfile?.name ?? "No profile selected"}</strong>
                </div>
              </div>
              <div className="admin-actions">
                <button
                  className="primary-button"
                  disabled={!selectedProfile || running}
                  type="button"
                  onClick={triggerAnalysis}
                >
                  {running ? "Running..." : "Run Analysis"}
                </button>
              </div>
            </article>
          </div>
          {message ? <div className="import-summary">{message}</div> : null}
        </>
      ) : null}
    </section>
  );
}
