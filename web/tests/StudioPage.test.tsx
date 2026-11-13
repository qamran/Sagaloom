import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { getMe, getStudio } from "@/lib/api";
import type { Me, SettingsPayload, StudioData } from "@/lib/types";
import StudioPage from "../app/studio/page";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/lib/world", () => ({
  useWorld: () => ({ world: { id: "w1", name: "Velmar" } }),
}));
vi.mock("@/lib/api", () => ({
  getMe: vi.fn(),
  getStudio: vi.fn(),
  getModels: vi.fn(async () => ({})),
  getSettings: vi.fn(async () => ({}) as SettingsPayload),
}));
// The panels have their own tests; here they only report whether Studio made them read-only.
const { panel } = vi.hoisted(() => ({
  panel:
    (name: string) =>
    ({ readOnly }: { readOnly?: boolean }) => <p data-testid={name}>{readOnly ? "read-only" : "editable"}</p>,
}));
vi.mock("@/components/ProvidersPanel", () => ({ ProvidersPanel: panel("providers") }));
vi.mock("@/components/SettingsPanel", () => ({ SettingsPanel: panel("settings") }));
vi.mock("@/components/GuardrailsPanel", () => ({ GuardrailsPanel: panel("guardrails") }));
vi.mock("@/components/ToolsPanel", () => ({ ToolsPanel: panel("tools") }));
vi.mock("@/components/MemoryPanel", () => ({ MemoryPanel: () => null }));
vi.mock("@/components/AgentGraph", () => ({ AgentGraph: () => null }));
vi.mock("@/components/FeatureMap", () => ({ FeatureMap: () => null }));

const studio: StudioData = {
  features: [],
  providers: [],
  usage: { prompt_tokens: 1, completion_tokens: 2, cost_usd: 0.01, by_model: [] },
  mermaid: "",
};
const me = (is_admin: boolean): Me => ({
  id: "user_a", email: "a@b.c", display_name: "A", is_admin, last_world_id: null,
  month_spend_usd: 0, monthly_budget_usd: is_admin ? null : 1, budget_resets_on: "2026-12-01", over_budget: false,
});
const setup = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <StudioPage />
    </QueryClientProvider>,
  );

beforeEach(() => {
  vi.mocked(getStudio).mockReset().mockResolvedValue(studio);
});

describe("Studio for a non-admin and the admin", () => {
  it("gives a non-admin read-only panels, their own usage, and no All users switch", async () => {
    vi.mocked(getMe).mockResolvedValue(me(false));
    setup();

    for (const name of ["providers", "settings", "guardrails", "tools"]) {
      expect(await screen.findByTestId(name)).toHaveTextContent("read-only");
    }
    // Only the world selected in the header.
    expect(getStudio).toHaveBeenCalledWith("mine", "w1");
    expect(getStudio).not.toHaveBeenCalledWith("all");
    expect(await screen.findByText("Showing Velmar only.")).toBeInTheDocument();
    expect(screen.queryByRole("switch", { name: "All users" })).toBeNull();
  });

  it("gives the admin editable panels and the All users switch", async () => {
    vi.mocked(getMe).mockResolvedValue(me(true));
    setup();

    expect(await screen.findByRole("switch", { name: "All users" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("settings")).toHaveTextContent("editable"));
    for (const name of ["providers", "guardrails", "tools"]) {
      expect(screen.getByTestId(name)).toHaveTextContent("editable");
    }
  });
});

describe("Studio shows the selected world", () => {
  it("asks for the header's world, and the admin's All users view drops it", async () => {
    vi.mocked(getMe).mockResolvedValue(me(true));
    setup();
    await waitFor(() => expect(getStudio).toHaveBeenCalledWith("mine", "w1"));
    expect(getStudio).not.toHaveBeenCalledWith("mine");

    await userEvent.click(
      await screen.findByRole("switch", { name: "All users" }),
    );
    await waitFor(() => expect(getStudio).toHaveBeenCalledWith("all", undefined));
    expect(
      await screen.findByText("Every user, every world."),
    ).toBeInTheDocument();
  });
});
