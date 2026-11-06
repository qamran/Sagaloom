import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AgentGraph } from "@/components/AgentGraph";
import { getLastRun, getThreads } from "@/lib/api";
import type { ThreadSummary } from "@/lib/types";

const summary = (thread_id: string, world_id: string, pending: number): ThreadSummary => ({
  thread_id, world_id, pending, created_at: "", kind: "chat", title: null, badge: null,
});

const mermaidMock = vi.hoisted(() => ({
  initialize: vi.fn(),
  render: vi.fn(),
}));
vi.mock("mermaid", () => ({ default: mermaidMock }));
vi.mock("@/lib/api", () => ({ getThreads: vi.fn(), getLastRun: vi.fn() }));
let search = "";
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(search) }));

const SRC = "graph TD;\n\tguard(guard)\n\trouter(router)\n\tguard --> router;\n";
const wrap = (ui: React.ReactNode) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      {ui}
    </QueryClientProvider>,
  );

beforeEach(() => {
  search = "";
  mermaidMock.initialize.mockReset();
  mermaidMock.render.mockReset().mockResolvedValue({ svg: "<svg data-testid='graph'></svg>" });
  vi.mocked(getThreads)
    .mockReset()
    .mockResolvedValue([
      summary("t1", "w", 0),
      summary("t2", "w", 0),
    ]);
  vi.mocked(getLastRun)
    .mockReset()
    .mockImplementation(async (id) => ({
      thread_id: id,
      nodes: id === "t2" ? ["guard", "router", "agent"] : ["guard"],
      paused: false,
    }));
});

describe("AgentGraph", () => {
  it("loads the last run for the picked thread and lists it in the caption", async () => {
    wrap(<AgentGraph mermaid={SRC} />);
    await waitFor(() => expect(getLastRun).toHaveBeenCalledWith("t1"));
    await userEvent.selectOptions(await screen.findByRole("combobox"), "t2");
    await waitFor(() => expect(getLastRun).toHaveBeenCalledWith("t2"));
    expect(await screen.findByText("Last run: guard → router → agent")).toBeInTheDocument();
    await waitFor(() => {
      const src = mermaidMock.render.mock.calls.at(-1)?.[1] as string;
      expect(src).toContain("class guard,router lastrun;");
    });
    expect(mermaidMock.initialize).toHaveBeenCalledWith(
      expect.objectContaining({ startOnLoad: false, theme: "dark" }),
    );
  });

  it("defaults to the ?thread= parameter", async () => {
    search = "thread=t2";
    wrap(<AgentGraph mermaid={SRC} />);
    await waitFor(() => expect(getLastRun).toHaveBeenCalledWith("t2"));
  });

  it("falls back to the source when rendering throws", async () => {
    mermaidMock.render.mockRejectedValue(new Error("boom"));
    const { container } = wrap(<AgentGraph mermaid={SRC} />);
    await waitFor(() => expect(container.querySelector("pre")?.textContent).toContain("guard --> router"));
  });

  it("falls back to the first thread when ?thread= is not in the list", async () => {
    search = "thread=gone";
    wrap(<AgentGraph mermaid={SRC} />);
    await waitFor(() => expect(getLastRun).toHaveBeenCalledWith("t1"));
    expect(await screen.findByRole("combobox")).toHaveValue("t1");
  });

  it("says when the run is waiting for approval", async () => {
    vi.mocked(getLastRun).mockResolvedValue({ thread_id: "t1", nodes: ["guard", "approval_gate"], paused: true });
    wrap(<AgentGraph mermaid={SRC} />);
    expect(await screen.findByText("Last run: guard → approval_gate (waiting for approval)")).toBeInTheDocument();
  });
});
