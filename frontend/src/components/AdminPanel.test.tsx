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
        status: 202,
        json: async () => ({
          status: "pending",
          summary: null,
          concern_level: null,
          highlights: [],
          advice: null,
          generated_at: null,
          measurement_count: 0,
          is_stale: false,
          error_message: null,
        }),
      });
    vi.stubGlobal("fetch", fetchMock);

    render(<AdminPanel selectedProfile={selectedProfile} />);

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
    });
    // The run finishes in the background; the result arrives over the live WebSocket.
    expect(
      await screen.findByText(/Analysis for Alex is running in the background/),
    ).toBeInTheDocument();
  });
});
