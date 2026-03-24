import { render, screen, waitFor } from "@testing-library/react";

import { App } from "./App";

const dashboardPayload = {
  profiles: [
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
  ],
  selected_profile_id: 1,
  measurements: [],
  charts: { profile_id: 1, series: {} },
};

describe("App", () => {
  it("remembers the selected profile from localStorage", async () => {
    window.localStorage.setItem("local-scale:selected-profile-id", "1");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => dashboardPayload,
        status: 200,
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => null,
        status: 200,
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => dashboardPayload,
        status: 200,
      });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal(
      "WebSocket",
      class {
        readyState = 1;
        onmessage: ((event: MessageEvent) => void) | null = null;
        onerror: (() => void) | null = null;
        close() {}
        send() {}
      },
    );

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole("combobox")).toHaveValue("1");
    });
    expect(fetchMock).toHaveBeenCalledWith("/api/dashboard?profile_id=1", undefined);
  });
});
