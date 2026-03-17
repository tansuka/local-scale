import { useEffect, useState } from "react";

import type { Profile } from "../lib/types";

type ProfileDraft = {
  name: string;
  sex: string;
  birth_date: string;
  height_cm: string;
  units: string;
  color: string;
  notes: string;
};

type ProfileFormProps = {
  selectedProfile?: Profile | null;
  onCreate: (payload: Omit<Profile, "id" | "active">) => Promise<Profile>;
  onUpdate: (
    profileId: number,
    payload: Omit<Profile, "id" | "active">,
  ) => Promise<Profile>;
  onSaved: (profile: Profile) => void | Promise<void>;
};

const DEFAULT_DRAFT: ProfileDraft = {
  name: "",
  sex: "female",
  birth_date: "",
  height_cm: "",
  units: "metric",
  color: "#0f766e",
  notes: "",
};

function draftFromProfile(profile: Profile | null | undefined): ProfileDraft {
  if (!profile) {
    return DEFAULT_DRAFT;
  }
  return {
    name: profile.name,
    sex: profile.sex,
    birth_date: profile.birth_date,
    height_cm: String(profile.height_cm),
    units: profile.units,
    color: profile.color,
    notes: profile.notes ?? "",
  };
}

export function ProfileForm({
  selectedProfile,
  onCreate,
  onUpdate,
  onSaved,
}: ProfileFormProps) {
  const [draft, setDraft] = useState<ProfileDraft>(draftFromProfile(selectedProfile));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [mode, setMode] = useState<"edit" | "create">("edit");

  useEffect(() => {
    setDraft(draftFromProfile(selectedProfile));
    setMode("edit");
    setMessage(null);
  }, [selectedProfile]);

  const save = async () => {
    const payload = {
      name: draft.name.trim(),
      sex: draft.sex,
      birth_date: draft.birth_date,
      height_cm: Number(draft.height_cm),
      units: draft.units,
      color: draft.color,
      notes: draft.notes.trim() || null,
    };
    setBusy(true);
    setMessage(null);
    try {
      const profile =
        mode === "create" || !selectedProfile
          ? await onCreate(payload)
          : await onUpdate(selectedProfile.id, payload);
      await onSaved(profile);
      setMode("edit");
      setMessage(mode === "create" ? "Profile created." : "Profile updated.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel profile-form-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Profile Details</p>
          <h2>{mode === "create" ? "Create a person" : "Edit selected person"}</h2>
        </div>
      </div>
      <div className="profile-form-grid">
        <label>
          <span>Name</span>
          <input
            value={draft.name}
            onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))}
          />
        </label>
        <label>
          <span>Sex</span>
          <select
            value={draft.sex}
            onChange={(event) => setDraft((current) => ({ ...current, sex: event.target.value }))}
          >
            <option value="female">Female</option>
            <option value="male">Male</option>
            <option value="other">Other</option>
          </select>
        </label>
        <label>
          <span>Birth date</span>
          <input
            type="date"
            value={draft.birth_date}
            onChange={(event) =>
              setDraft((current) => ({ ...current, birth_date: event.target.value }))
            }
          />
        </label>
        <label>
          <span>Height (cm)</span>
          <input
            type="number"
            min="1"
            value={draft.height_cm}
            onChange={(event) =>
              setDraft((current) => ({ ...current, height_cm: event.target.value }))
            }
          />
        </label>
        <label>
          <span>Accent color</span>
          <input
            type="color"
            value={draft.color}
            onChange={(event) => setDraft((current) => ({ ...current, color: event.target.value }))}
          />
        </label>
        <label>
          <span>Units</span>
          <select
            value={draft.units}
            onChange={(event) =>
              setDraft((current) => ({ ...current, units: event.target.value }))
            }
          >
            <option value="metric">Metric</option>
          </select>
        </label>
        <label className="profile-form-notes">
          <span>Notes</span>
          <textarea
            rows={3}
            value={draft.notes}
            onChange={(event) => setDraft((current) => ({ ...current, notes: event.target.value }))}
          />
        </label>
      </div>
      <div className="profile-form-actions">
        <button className="ghost-button" type="button" onClick={() => {
          setMode("create");
          setDraft(DEFAULT_DRAFT);
          setMessage(null);
        }}>
          New Profile
        </button>
        <button className="primary-button" disabled={busy} type="button" onClick={save}>
          {busy ? "Saving..." : mode === "create" ? "Create Profile" : "Save Changes"}
        </button>
      </div>
      {message ? <div className="import-summary">{message}</div> : null}
    </section>
  );
}
