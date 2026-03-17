import type { Profile } from "../lib/types";

type ProfileSwitcherProps = {
  profiles: Profile[];
  selectedProfileId?: number | null;
  onSelect: (profileId: number) => void;
};

export function ProfileSwitcher({
  profiles,
  selectedProfileId,
  onSelect,
}: ProfileSwitcherProps) {
  return (
    <div className="profile-switcher">
      <label className="profile-switcher-label" htmlFor="profile-switcher">
        User
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
