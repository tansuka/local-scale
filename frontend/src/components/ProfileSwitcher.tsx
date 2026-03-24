import type { Profile } from "../lib/types";

type ProfileSwitcherProps = {
  profiles: Profile[];
  selectedProfileId?: number | null;
  label?: string;
  stacked?: boolean;
  onSelect: (profileId: number) => void;
};

export function ProfileSwitcher({
  profiles,
  selectedProfileId,
  label = "User",
  stacked = false,
  onSelect,
}: ProfileSwitcherProps) {
  return (
    <div className={`profile-switcher ${stacked ? "stacked" : ""}`}>
      <label className="profile-switcher-label" htmlFor="profile-switcher">
        {label}
      </label>
      <select
        id="profile-switcher"
        className="profile-select"
        value={selectedProfileId ?? ""}
        onChange={(event) => onSelect(Number(event.target.value))}
      >
        {profiles.map((profile) => (
          <option key={profile.id} value={profile.id}>
            {profile.name}
          </option>
        ))}
      </select>
    </div>
  );
}
