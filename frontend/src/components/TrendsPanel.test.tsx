import { fireEvent, render, screen } from "@testing-library/react";

const setOptionMock = vi.fn();

vi.mock("echarts", () => ({
  init: () => ({
    setOption: setOptionMock,
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
    waist_cm: 84,
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
    skeletal_muscle_weight_kg: 31.2,
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
    source_metric_map: {
      fat_pct: "anthropometric_estimated",
      water_pct: "anthropometric_estimated",
      skeletal_muscle_weight_kg: "anthropometric_estimated",
    },
    raw_payload_json: {},
  },
];

const charts = {
  profile_id: 1,
  series: {
    weight_kg: [{ measured_at: "2026-03-18T12:00:00Z", value: 72.5 }],
    fat_pct: [{ measured_at: "2026-03-18T12:00:00Z", value: 18.4 }],
    water_pct: [],
    muscle_pct: [{ measured_at: "2026-03-18T12:00:00Z", value: 45.3 }],
    skeletal_muscle_weight_kg: [{ measured_at: "2026-03-18T12:00:00Z", value: 31.2 }],
    visceral_fat: [{ measured_at: "2026-03-18T12:00:00Z", value: 8 }],
    bmi: [{ measured_at: "2026-03-18T12:00:00Z", value: 22.1 }],
    bmr_kcal: [{ measured_at: "2026-03-18T12:00:00Z", value: 1700 }],
  },
};

describe("TrendsPanel", () => {
  beforeEach(() => {
    setOptionMock.mockClear();
  });

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
    expect(setOptionMock).toHaveBeenCalled();
    const latestOption = setOptionMock.mock.calls[setOptionMock.mock.calls.length - 1]?.[0];
    expect(latestOption?.yAxis?.min).toBe(62);
    expect(latestOption?.yAxis?.max).toBe(83);

    fireEvent.click(screen.getByRole("button", { name: "Fat %" }));

    expect(screen.getByRole("heading", { name: "Fat % over time" })).toBeInTheDocument();
  });

  it("recovers cleanly after switching to a metric with no values", () => {
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

    fireEvent.click(screen.getByRole("button", { name: "Water %" }));
    expect(
      screen.getByText("No water % data in this range yet. Try another time window."),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Weight" }));
    expect(screen.getByRole("heading", { name: "Weight over time" })).toBeInTheDocument();
  });

  it("explains anthropometric estimates in the history view", () => {
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

    expect(
      screen.getByText(
        "Estimated fat, water, and skeletal muscle values are inferred from sex, age, height, and weight when the scale does not provide them.",
      ),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Est.").length).toBeGreaterThan(0);
  });
});
