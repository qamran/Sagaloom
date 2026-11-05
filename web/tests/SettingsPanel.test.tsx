import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsPanel } from "@/components/SettingsPanel";
import { putSettings } from "@/lib/api";
import type { SettingsPayload } from "@/lib/types";

vi.mock("@/lib/api", () => ({
  putSettings: vi.fn(),
  ApiError: class ApiError extends Error {
    constructor(
      public status: number,
      message: string,
      public detail?: string,
    ) {
      super(message);
    }
  },
}));

const payload: SettingsPayload = {
  settings: { agent_temperature: 0.2, agent_max_tokens: 1000, agent_system_prompt: null, guard_enabled: true, enabled_tools: null },
  defaults: { agent_system_prompt: "You are the Sagaloom agent." },
  guard_policy: "policy text",
};

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <SettingsPanel payload={payload} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.mocked(putSettings).mockReset().mockResolvedValue(payload);
});

describe("SettingsPanel", () => {
  it("shows the current values", () => {
    setup();
    expect(screen.getByLabelText("Agent temperature")).toHaveValue(0.2);
    expect(screen.getByLabelText("Agent max tokens")).toHaveValue(1000);
    expect(screen.getByLabelText("Agent system prompt")).toHaveValue("You are the Sagaloom agent.");
  });

  it("saves a changed temperature as a partial patch", async () => {
    setup();
    const t = screen.getByLabelText("Agent temperature");
    await userEvent.clear(t);
    await userEvent.type(t, "0.7");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(putSettings).toHaveBeenCalledWith({ agent_temperature: 0.7 }));
  });

  it("clearing max tokens sends null", async () => {
    setup();
    await userEvent.clear(screen.getByLabelText("Agent max tokens"));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(putSettings).toHaveBeenCalledWith({ agent_max_tokens: null }));
  });

  it("Reset to default sends reset_system_prompt", async () => {
    setup();
    await userEvent.click(screen.getByRole("button", { name: "Reset to default" }));
    await waitFor(() => expect(putSettings).toHaveBeenCalledWith({ reset_system_prompt: true }));
  });

  it("shows the server detail on a 422", async () => {
    const { ApiError } = await import("@/lib/api");
    vi.mocked(putSettings).mockRejectedValue(new ApiError(422, "422 Unprocessable", "agent_max_tokens must be 256 or more"));
    setup();
    await userEvent.type(screen.getByLabelText("Agent system prompt"), "x");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("agent_max_tokens must be 256 or more");
  });

  it("disables Save for a temperature outside 0 to 2", async () => {
    setup();
    const t = screen.getByLabelText("Agent temperature");
    await userEvent.clear(t);
    await userEvent.type(t, "2.5");
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("has no inputs for judge, extractor or guard temperature", () => {
    setup();
    expect(screen.queryByLabelText(/judge|extractor|guard/i)).toBeNull();
  });
});
