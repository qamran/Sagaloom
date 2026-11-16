import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RouterEnginePanel } from "@/components/RouterEnginePanel";
import { putSettings } from "@/lib/api";
import type { SettingsPayload } from "@/lib/types";

vi.mock("@/lib/api", () => ({ putSettings: vi.fn() }));

const payload = (router_engine: "llm" | "jev"): SettingsPayload => ({
  settings: { agent_temperature: 0, agent_max_tokens: null, agent_system_prompt: null, guard_enabled: true, router_engine, enabled_tools: null, monthly_budget_usd: 1 },
  defaults: { agent_system_prompt: "x" },
  guard_policy: "p",
});

function setup(p: SettingsPayload, readOnly = false) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <RouterEnginePanel payload={p} readOnly={readOnly} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.mocked(putSettings).mockReset().mockResolvedValue(payload("llm"));
});

describe("RouterEnginePanel", () => {
  it("shows current engine", () => {
    setup(payload("jev"));
    expect(screen.getByRole("radiogroup", { name: "Router engine" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Jev decision model" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "LLM (default)" })).not.toBeChecked();
    expect(screen.getByText(/Jev answers one typed question/)).toBeInTheDocument();
  });

  it("switching calls putSettings", async () => {
    setup(payload("jev"));
    await userEvent.click(screen.getByRole("radio", { name: "LLM (default)" }));
    await waitFor(() => expect(putSettings).toHaveBeenCalledWith({ router_engine: "llm" }));
    await waitFor(() => expect(screen.getByRole("radio", { name: "LLM (default)" })).toBeChecked());
  });

  it("read-only disables and shows admin note", () => {
    setup(payload("llm"), true);
    expect(screen.getByRole("radio", { name: "LLM (default)" })).toBeDisabled();
    expect(screen.getByRole("radio", { name: "Jev decision model" })).toBeDisabled();
    expect(screen.getByText("Only the admin can change developer settings.")).toBeInTheDocument();
  });

  it("save failure shows error", async () => {
    vi.mocked(putSettings).mockRejectedValue(new Error("boom"));
    setup(payload("llm"));
    await userEvent.click(screen.getByRole("radio", { name: "Jev decision model" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The router engine was not saved. Try again.");
    expect(screen.getByRole("radio", { name: "LLM (default)" })).toBeChecked();
  });
});
