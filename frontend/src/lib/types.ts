export type Profile = {
  id: number;
  name: string;
  sex: string;
  birth_date: string;
  height_cm: number;
  units: string;
  color: string;
  notes?: string | null;
  active: boolean;
};

export type Measurement = {
  id: number;
  profile_id: number;
  measured_at: string;
  source: string;
  assignment_state: string;
  confidence: number;
  anomaly_score: number;
  note?: string | null;
  weight_kg: number;
  waist_cm?: number | null;
  triglycerides_mmol_l?: number | null;
  hdl_mmol_l?: number | null;
  bmi?: number | null;
  fat_pct?: number | null;
  fat_weight_kg?: number | null;
  skeletal_muscle_pct?: number | null;
  skeletal_muscle_weight_kg?: number | null;
  muscle_pct?: number | null;
  muscle_weight_kg?: number | null;
  visceral_fat?: number | null;
  visceral_adiposity_index?: number | null;
  water_pct?: number | null;
  water_weight_kg?: number | null;
  bone_weight_kg?: number | null;
  bmr_kcal?: number | null;
  metabolic_age?: number | null;
  body_age?: number | null;
  status_by_metric: Record<string, string>;
  source_metric_map: Record<string, string>;
  raw_payload_json: Record<string, unknown>;
};

export type ChartPoint = {
  measured_at: string;
  value: number;
};

export type ChartResponse = {
  profile_id: number;
  series: Record<string, ChartPoint[]>;
};

export type WeighSession = {
  id: string;
  selected_profile_id: number;
  status: string;
  adapter_mode: string;
  started_at: string;
  expires_at: string;
  completed_at?: string | null;
  measurement_id?: number | null;
  anomaly_score?: number | null;
  requires_confirmation: boolean;
  error_message?: string | null;
};

export type DashboardPayload = {
  profiles: Profile[];
  selected_profile_id?: number | null;
  measurements: Measurement[];
  charts?: ChartResponse | null;
  health_analysis?: HealthAnalysis | null;
};

export type HealthAnalysis = {
  status: "ready" | "pending" | "not_configured" | "no_data" | "error";
  summary?: string | null;
  concern_level?: "low" | "moderate" | "high" | null;
  highlights: string[];
  advice?: string | null;
  generated_at?: string | null;
  measurement_count: number;
  is_stale: boolean;
  error_message?: string | null;
};

export type LlmSettings = {
  base_url: string;
  model: string;
  has_api_key: boolean;
  api_key_preview?: string | null;
  prompt_path: string;
  prompt_loaded: boolean;
  prompt_error?: string | null;
};

export type ImportPreviewRow = {
  row_number: number;
  measured_at?: string | null;
  profile_name?: string | null;
  weight_kg?: number | null;
  waist_cm?: number | null;
  bmi?: number | null;
  fat_pct?: number | null;
  water_pct?: number | null;
  muscle_pct?: number | null;
  notes: string[];
};

export type ImportPreviewResponse = {
  source_name: string;
  inferred_columns: Record<string, string>;
  rows: ImportPreviewRow[];
  warnings: string[];
};

export type ImportCommitResponse = {
  batch_id: number;
  imported: number;
  skipped: number;
  errors: Array<Record<string, unknown>>;
};

export type LiveEvent =
  | { type: "session.updated"; session: WeighSession; details?: Record<string, unknown> }
  | { type: "measurement.created"; measurement: Measurement };
