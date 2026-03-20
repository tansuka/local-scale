import { fireEvent, render, screen } from "@testing-library/react";

vi.mock("echarts", () => ({
  init: () => ({
    setOption() {},
    resize() {},
    dispose() {},
  }),
}));

import { TrendsPanel } from "./TrendsPanel";

const profiles = [
  {
    id: 1,
    name: "Alex",
    sex: "male",
    birth_date: "1989-08-17",
    height_cm: 181,
    units: "metric",
    color: "#0f766e",
    active: true,
    notes: null,
  },
];

const measurements = [
  {
    id: 1,
    profile_id: 1,
    measured_at: "2026-03-18T12:00:00Z",
    source: "replay",
    assignment_state: "confirmed",
    confidence: 1,
    anomaly_score: 0,
    note: null,
    weight_kg: 72.5,
    bmi: 22.1,
    fat_pct: 18.4,
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
    body_age: null,
    status_by_metric: {},
    source_metric_map: {},
    raw_payload_json: {},
  },
];

const charts = {
  profile_id: 1,
  series: {
    weight_kg: [{ measured_at: "2026-03-18T12:00:00Z", value: 72.5 }],
    fat_pct: [{ measured_at: "2026-03-18T12:00:00Z", value: 18.4 }],
    water_pct: [{ measured_at: "2026-03-18T12:00:00Z", value: 56.2 }],
    muscle_pct: [{ measured_at: "2026-03-18T12:00:00Z", value: 45.3 }],
    skeletal_muscle_pct: [{ measured_at: "2026-03-18T12:00:00Z", value: 40.1 }],
    visceral_fat: [{ measured_at: "2026-03-18T12:00:00Z", value: 8 }],
    bmi: [{ measured_at: "2026-03-18T12:00:00Z", value: 22.1 }],
    bmr_kcal: [{ measured_at: "2026-03-18T12:00:00Z", value: 1700 }],
  },
};

describe("TrendsPanel", () => {
  it("defaults to weight and switches headings when the metric changes", () => {
    render(
      <TrendsPanel
        charts={charts}
        measurements={measurements}
        onDelete={async () => {}}
        onReassign={async () => {}}
        profiles={profiles}
        selectedProfileId={1}
      />,
    );

    expect(screen.getByRole("heading", { name: "Weight over time" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "All weigh-ins in this range" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Fat %" }));

    expect(screen.getByRole("heading", { name: "Fat % over time" })).toBeInTheDocument();
  });
});
