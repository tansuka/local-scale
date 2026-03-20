import { render, screen } from "@testing-library/react";

import { LiveSessionCard } from "./LiveSessionCard";

describe("LiveSessionCard", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows cancel controls and remaining time for an active session", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-03-20T12:00:00.000Z"));

    render(
      <LiveSessionCard
        cancelling={false}
        details={null}
        loading={false}
        onCancel={() => {}}
        onStart={() => {}}
        selectedProfile={{
          id: 1,
          name: "Alex",
          sex: "male",
          birth_date: "1989-08-17",
          height_cm: 181,
          units: "metric",
          color: "#0f766e",
          active: true,
          notes: null,
        }}
        session={{
          id: "session-1",
          selected_profile_id: 1,
          status: "capturing",
          adapter_mode: "live",
          started_at: "2026-03-20T11:59:30.000Z",
          expires_at: "2026-03-20T12:00:45.000Z",
          completed_at: null,
          measurement_id: null,
          anomaly_score: null,
          requires_confirmation: false,
          error_message: null,
        }}
      />,
    );

    expect(screen.getByRole("button", { name: "Weigh-In Running" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeEnabled();
    expect(screen.getByText("Time remaining: 0:45")).toBeInTheDocument();
    expect(
      screen.getByText("Scan ends automatically when the timer runs out."),
    ).toBeInTheDocument();
  });
});
