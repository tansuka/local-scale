import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { HistoryTable } from "./HistoryTable";

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

const measurement = {
  id: 1,
  profile_id: 1,
  measured_at: "2026-03-18T12:00:00Z",
  source: "ios_bluetooth",
  assignment_state: "confirmed",
  confidence: 1,
  anomaly_score: 0,
  note: null,
  weight_kg: 72.5,
  waist_cm: 84,
  triglycerides_mmol_l: 1.1,
  hdl_mmol_l: 1.4,
  bmi: 22.1,
  fat_pct: 18.4,
  fat_weight_kg: null,
  skeletal_muscle_pct: 40.1,
  skeletal_muscle_weight_kg: 31.2,
  muscle_pct: null,
  muscle_weight_kg: null,
  visceral_adiposity_index: 1.8,
  water_pct: 56.2,
  water_weight_kg: null,
  bone_weight_kg: null,
  bmr_kcal: 1700,
  metabolic_age: null,
  body_age: null,
  status_by_metric: {},
  source_metric_map: {},
  raw_payload_json: {},
};

function renderTable(onUpdateMeasurement = vi.fn(async () => {})) {
  render(
    <HistoryTable
      measurements={[measurement]}
      profiles={profiles}
      selectedProfileId={1}
      onDelete={async () => {}}
      onReassign={async () => {}}
      onUpdateMeasurement={onUpdateMeasurement}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Edit" }));
  return onUpdateMeasurement;
}

describe("HistoryTable lab editor", () => {
  it("sends only the field that was edited", async () => {
    const onUpdateMeasurement = renderTable();

    fireEvent.change(screen.getByLabelText("HDL for measurement 1"), {
      target: { value: "1.5" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(onUpdateMeasurement).toHaveBeenCalledWith(1, { hdl_mmol_l: 1.5 });
    });
  });

  it("sends null when a field is emptied", async () => {
    const onUpdateMeasurement = renderTable();

    fireEvent.change(screen.getByLabelText("Waist for measurement 1"), {
      target: { value: "" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(onUpdateMeasurement).toHaveBeenCalledWith(1, { waist_cm: null });
    });
  });

  it("does not call the API when nothing was edited", async () => {
    const onUpdateMeasurement = renderTable();

    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    });
    expect(onUpdateMeasurement).not.toHaveBeenCalled();
  });
});
