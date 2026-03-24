import type {
  ChartResponse,
  DashboardPayload,
  ImportCommitResponse,
  ImportPreviewResponse,
  Measurement,
  Profile,
  WeighSession,
} from "./types";

async function request<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Request failed with ${response.status}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function fetchDashboard(profileId?: number | null): Promise<DashboardPayload> {
  const search = profileId ? `?profile_id=${profileId}` : "";
  return request<DashboardPayload>(`/api/dashboard${search}`);
}

export function fetchCurrentSession(): Promise<WeighSession | null> {
  return request<WeighSession | null>("/api/sessions/current");
}

export function startSession(selectedProfileId: number): Promise<WeighSession> {
  return request<WeighSession>("/api/sessions/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ selected_profile_id: selectedProfileId }),
  });
}

export function cancelSession(sessionId: string): Promise<WeighSession> {
  return request<WeighSession>(`/api/sessions/${sessionId}/cancel`, {
    method: "POST",
  });
}

export function reassignMeasurement(
  measurementId: number,
  profileId: number,
): Promise<Measurement> {
  return request<Measurement>(`/api/measurements/${measurementId}/reassign-profile`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile_id: profileId }),
  });
}

export function deleteMeasurement(measurementId: number): Promise<void> {
  return request<void>(`/api/measurements/${measurementId}`, {
    method: "DELETE",
  });
}

export function updateMeasurement(
  measurementId: number,
  payload: {
    waist_cm?: number | null;
    triglycerides_mmol_l?: number | null;
    hdl_mmol_l?: number | null;
  },
): Promise<Measurement> {
  return request<Measurement>(`/api/measurements/${measurementId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function fetchCharts(profileId: number): Promise<ChartResponse> {
  return request<ChartResponse>(`/api/charts/${profileId}`);
}

export function createProfile(payload: Omit<Profile, "id" | "active">): Promise<Profile> {
  return request<Profile>("/api/profiles", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function updateProfile(
  profileId: number,
  payload: Omit<Profile, "id" | "active">,
): Promise<Profile> {
  return request<Profile>(`/api/profiles/${profileId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function previewImport(file: File): Promise<ImportPreviewResponse> {
  const body = new FormData();
  body.append("file", file);
  return request<ImportPreviewResponse>("/api/imports/csv/preview", {
    method: "POST",
    body,
  });
}

export async function commitImport(
  file: File,
  profileId?: number,
): Promise<ImportCommitResponse> {
  const body = new FormData();
  body.append("file", file);
  if (profileId) {
    body.append("profile_id", String(profileId));
  }
  return request<ImportCommitResponse>("/api/imports/csv/commit", {
    method: "POST",
    body,
  });
}
