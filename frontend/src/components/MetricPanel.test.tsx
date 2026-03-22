import { fireEvent, render, screen } from "@testing-library/react";

import { MetricPanel } from "./MetricPanel";

const measurement = {
  id: 1,
  profile_id: 1,
  measured_at: "2026-03-22T08:15:00Z",
  source: "replay",
  assignment_state: "confirmed",
  confidence: 1,
  anomaly_score: 0,
  note: null,
  weight_kg: 72.4,
  bmi: 25.7,
  fat_pct: 23.2,
  fat_weight_kg: null,
  skeletal_muscle_pct: 40.1,
  skeletal_muscle_weight_kg: null,
  muscle_pct: 45.3,
  muscle_weight_kg: null,
  visceral_fat: 8,
  water_pct: 56.2,
  water_weight_kg: null,
  bone_weight_kg: null,
  bmr_kcal: 1700,
  metabolic_age: null,
  body_age: 30,
  status_by_metric: {
    bmi: "high",
    fat_pct: "high",
    muscle_pct: "healthy",
    water_pct: "healthy",
    visceral_fat: "healthy",
  },
  source_metric_map: {},
  raw_payload_json: {},
};

const profile = {
  id: 1,
  name: "Alex",
  sex: "male",
  birth_date: "1989-08-17",
  height_cm: 181,
  units: "metric",
  color: "#0f766e",
  active: true,
  notes: null,
};

describe("MetricPanel", () => {
  it("shows a selectable metric detail view", () => {
    render(<MetricPanel measurement={measurement} profile={profile} />);

    expect(screen.getByRole("heading", { name: "Weight" })).toBeInTheDocument();
    expect(screen.getByText("Low")).toBeInTheDocument();
    expect(screen.getByText("Healthy")).toBeInTheDocument();
    expect(screen.getByText("High")).toBeInTheDocument();
    expect(screen.getByText("Obese")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /BMI/i }));

    expect(screen.getByRole("heading", { name: "BMI" })).toBeInTheDocument();
    expect(
      screen.getByText(
        "BMI is a quick weight-to-height screening number. It is useful for trend tracking, but it should be read alongside fat, muscle, and water.",
      ),
    ).toBeInTheDocument();
  });
});
