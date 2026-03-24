import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { AdminPanel } from "./AdminPanel";

const selectedProfile = {
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

describe("AdminPanel", () => {
  it("loads settings, saves updates, and triggers a manual analysis run", async () => {
    const onAnalysisUpdated = vi.fn();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          base_url: "http://localhost:11434/v1",
          model: "llama3",
          has_api_key: true,
          api_key_preview: "******1234",
          prompt_path: "/tmp/llm-health-prompt.txt",
          prompt_loaded: true,
          prompt_error: null,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          base_url: "http://localhost:11434/v1",
          model: "gpt-4.1-mini",
          has_api_key: true,
          api_key_preview: "******1234",
          prompt_path: "/tmp/llm-health-prompt.txt",
          prompt_loaded: true,
          prompt_error: null,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          status: "ready",
          summary: "Fresh analysis summary.",
          concern_level: "moderate",
          highlights: ["Hydration dipped slightly."],
          advice: "Drink a little more water tomorrow.",
          generated_at: "2026-03-24T10:00:00Z",
          measurement_count: 7,
          is_stale: false,
          error_message: null,
        }),
      });
    vi.stubGlobal("fetch", fetchMock);

    render(<AdminPanel selectedProfile={selectedProfile} onAnalysisUpdated={onAnalysisUpdated} />);

    expect(await screen.findByDisplayValue("http://localhost:11434/v1")).toBeInTheDocument();

    fireEvent.change(screen.getByDisplayValue("llama3"), {
      target: { value: "gpt-4.1-mini" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save LLM Settings" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/admin/llm-settings",
        expect.objectContaining({ method: "PUT" }),
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "Run Analysis" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/admin/profiles/1/health-analysis/run",
        expect.objectContaining({ method: "POST" }),
      );
      expect(onAnalysisUpdated).toHaveBeenCalledWith(
        expect.objectContaining({ summary: "Fresh analysis summary." }),
      );
    });
  });
});
