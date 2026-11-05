import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToolsPanel } from "@/components/ToolsPanel";
import { getTools, putSettings } from "@/lib/api";
import type { SettingsPayload, ToolInfo } from "@/lib/types";

vi.mock("@/lib/api", () => ({ getTools: vi.fn(), putSettings: vi.fn() }));

const TOOLS: ToolInfo[] = [
  { name: "search_canon", description: "Search the canon.", core: true, enabled: true },
  { name: "create_or_update_entry", description: "Propose an entry.", core: true, enabled: true },
  { name: "check_contradiction", description: "Check a claim.", core: true, enabled: true },
  { name: "export_world", description: "Export the world.", core: false, enabled: true },
  { name: "real_world_reference", description: "Look up Wikipedia.", core: false, enabled: true },
];
const payload = {} as SettingsPayload;

let qc: QueryClient;
function setup(tools = TOOLS) {
  vi.mocked(getTools).mockResolvedValue(tools);
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ToolsPanel />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.mocked(getTools).mockReset();
  vi.mocked(putSettings).mockReset().mockResolvedValue(payload);
});

describe("ToolsPanel", () => {
  it("lists each tool with its description", async () => {
    setup();
    for (const t of TOOLS) {
      expect(await screen.findByText(t.name)).toBeInTheDocument();
      expect(screen.getByText(t.description)).toBeInTheDocument();
    }
  });

  it("shows core tools as an always-on disabled switch", async () => {
    setup();
    const sw = await screen.findByRole("switch", { name: /search_canon/ });
    expect(sw).toBeDisabled();
    expect(sw).toBeChecked();
    expect(within(sw).getByText("Always on")).toBeInTheDocument();
  });

  it("sends the other enabled optional tools when one is turned off", async () => {
    setup();
    await userEvent.click(await screen.findByRole("switch", { name: /export_world/ }));
    await waitFor(() => expect(putSettings).toHaveBeenCalledWith({ enabled_tools: ["real_world_reference"] }));
  });

  it("turns an optional tool back on alongside the enabled ones", async () => {
    setup(TOOLS.map((t) => (t.name === "export_world" ? { ...t, enabled: false } : t)));
    const sw = await screen.findByRole("switch", { name: /export_world/ });
    expect(sw).not.toBeChecked();
    await userEvent.click(sw);
    await waitFor(() =>
      expect(putSettings).toHaveBeenCalledWith({ enabled_tools: ["export_world", "real_world_reference"] }),
    );
  });

  it("invalidates tools, settings and studio after saving", async () => {
    setup();
    const spy = vi.spyOn(qc, "invalidateQueries");
    await userEvent.click(await screen.findByRole("switch", { name: /real_world_reference/ }));
    await waitFor(() => {
      const keys = spy.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey: unknown }).queryKey));
      expect(keys).toEqual(expect.arrayContaining(['["tools"]', '["settings"]', '["studio"]']));
    });
  });

  it("shows an error when the save fails", async () => {
    vi.mocked(putSettings).mockRejectedValue(new Error("x"));
    setup();
    await userEvent.click(await screen.findByRole("switch", { name: /export_world/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("not saved");
  });
});
