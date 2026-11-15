import { QueryClient, QueryClientProvider, QueryObserver } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToolsPanel } from "@/components/ToolsPanel";
import { TOOL_TESTS } from "@/lib/toolTests";
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

  it("shows core tools as plain Always on text, not a switch", async () => {
    setup();
    const card = (await screen.findByText("search_canon")).closest("li") as HTMLElement;
    expect(within(card).queryByRole("switch")).toBeNull();
    const label = within(card).getByText("Always on");
    expect(label.closest("button")).toBeNull();
    expect(label).toHaveAttribute("title", expect.stringContaining("cannot be turned off"));
    // A switchable tool does have a switch.
    expect(screen.getByRole("switch", { name: "export_world" })).toBeChecked();
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

  it("a tool toggle does not refetch the model list", async () => {
    setup();
    const settings = vi.fn().mockResolvedValue(payload);
    const models = vi.fn().mockResolvedValue([]);
    await qc.fetchQuery({ queryKey: ["settings"], queryFn: settings });
    await qc.fetchQuery({ queryKey: ["settings", "models"], queryFn: models });
    const observe = (queryKey: string[], queryFn: () => Promise<unknown>) =>
      new QueryObserver(qc, { queryKey, queryFn, staleTime: Infinity }).subscribe(() => {});
    const off = [observe(["settings"], settings), observe(["settings", "models"], models)];
    try {
      await userEvent.click(await screen.findByRole("switch", { name: /export_world/ }));
      await waitFor(() => expect(settings).toHaveBeenCalledTimes(2));
      expect(models).toHaveBeenCalledTimes(1);
    } finally {
      off.forEach((f) => f());
    }
  });

  it("shows an error when the save fails", async () => {
    vi.mocked(putSettings).mockRejectedValue(new Error("x"));
    setup();
    await userEvent.click(await screen.findByRole("switch", { name: /export_world/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("not saved");
  });
});

describe("ToolsPanel read-only", () => {
  it("disables the switches and says why for a non-admin", async () => {
    vi.mocked(getTools).mockResolvedValue(TOOLS);
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <ToolsPanel readOnly />
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("switch", { name: "export_world" })).toBeDisabled();
    expect(screen.getByText("Only the admin can change developer settings.")).toBeInTheDocument();
  });
});

describe("ToolsPanel cards", () => {
  it("gives each tool a one-line summary, a Try it message with a Chat link, and what to expect", async () => {
    setup();
    const card = (await screen.findByText("search_canon")).closest("li") as HTMLElement;
    expect(within(card).getByText(TOOL_TESTS.search_canon.summary)).toBeInTheDocument();
    expect(within(card).getByText("How many moons does Velmar have?")).toBeInTheDocument();
    expect(within(card).getByText(/cites entry ids/)).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: /Open in Chat/ })).toHaveAttribute(
      "href",
      "/chat?prompt=How%20many%20moons%20does%20Velmar%20have%3F",
    );
  });

  it("folds the agent's long instructions under What the agent is told", async () => {
    setup();
    const card = (await screen.findByText("export_world")).closest("li") as HTMLElement;
    const told = within(card).getByText("What the agent is told").closest("details") as HTMLDetailsElement;
    expect(told.open).toBe(false);
    expect(within(told).getByText("Export the world.")).toBeInTheDocument();
  });

  it("covers every tool the agent has", () => {
    for (const name of [
      "search_canon", "create_or_update_entry", "check_contradiction", "export_world",
      "real_world_reference", "remember_preference", "import_wiki",
    ]) {
      expect(TOOL_TESTS[name]?.summary, name).toBeTruthy();
      expect(TOOL_TESTS[name]?.prompt, name).toBeTruthy();
      expect(TOOL_TESTS[name]?.expect, name).toBeTruthy();
    }
  });

  it("says in one line how to test a tool and its switch", async () => {
    setup();
    expect(await screen.findByText(/send it again to test the switch/)).toBeInTheDocument();
    expect(screen.getByText(/sample world Velmar/)).toBeInTheDocument();
  });
});
