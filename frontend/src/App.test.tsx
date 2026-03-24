import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { App } from "./App";

const dashboardPayload = {
  profiles: [
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
  ],
  selected_profile_id: 1,
  measurements: [],
  charts: { profile_id: 1, series: {} },
  health_analysis: {
    status: "ready",
    summary: "Stable overall health trend.",
    concern_level: "low",
    highlights: ["Weight is steady."],
    generated_at: "2026-03-24T10:00:00Z",
    measurement_count: 4,
    is_stale: false,
    error_message: null,
  },
};

describe("App", () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.style.colorScheme = "";
  });

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

    fireEvent.click(await screen.findByRole("button", { name: "Open user menu" }));

    await waitFor(() => {
      expect(screen.getByRole("combobox")).toHaveValue("1");
    });
    expect(fetchMock).toHaveBeenCalledWith("/api/dashboard?profile_id=1", undefined);
  });

  it("persists the chosen color theme", async () => {
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

    const toggle = await screen.findByRole("button", { name: "Switch to dark mode" });
    fireEvent.click(toggle);

    await waitFor(() => {
      expect(window.localStorage.getItem("local-scale:theme")).toBe("dark");
      expect(document.documentElement.dataset.theme).toBe("dark");
      expect(document.documentElement.style.colorScheme).toBe("dark");
    });
  });

  it("renders the LLM health summary in the selected profile card", async () => {
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

    expect(await screen.findByText("Stable overall health trend.")).toBeInTheDocument();
    expect(screen.getByText("Low concern")).toBeInTheDocument();
  });
});
