import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AgentGraph } from "@/components/AgentGraph";
import { getLastRun, getThreads } from "@/lib/api";
import type { ThreadSummary } from "@/lib/types";

const summary = (thread_id: string, world_id: string, pending: number, over: Partial<ThreadSummary> = {}): ThreadSummary => ({
  thread_id, world_id, pending, created_at: "", kind: "chat", title: `Chat ${thread_id}`, badge: null, approved: 0, rejected: 0,
  running: false, ...over,
});

const mermaidMock = vi.hoisted(() => ({
  initialize: vi.fn(),
  render: vi.fn(),
}));
vi.mock("mermaid", () => ({ default: mermaidMock }));
vi.mock("@/lib/api", () => ({ getThreads: vi.fn(), getLastRun: vi.fn() }));
vi.mock("@/lib/world", () => ({ useWorld: () => ({ world: { id: "w", name: "Velmar" } }) }));
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

  it("an unknown thread param makes no last-run request for it", async () => {
    search = "thread=gone";
    wrap(<AgentGraph mermaid={SRC} />);
    await waitFor(() => expect(getLastRun).toHaveBeenCalledWith("t1"));
    expect(getLastRun).not.toHaveBeenCalledWith("gone");
  });

  it("makes no last-run request before the thread list has loaded", async () => {
    search = "thread=t2";
    let release: (v: ThreadSummary[]) => void = () => {};
    vi.mocked(getThreads).mockReturnValue(new Promise((r) => (release = r)));
    wrap(<AgentGraph mermaid={SRC} />);
    await act(async () => {});
    expect(getLastRun).not.toHaveBeenCalled();
    await act(async () => release([summary("t1", "w", 0), summary("t2", "w", 0)]));
    await waitFor(() => expect(getLastRun).toHaveBeenCalledWith("t2"));
  });

  it("says when the run is waiting for approval", async () => {
    vi.mocked(getLastRun).mockResolvedValue({ thread_id: "t1", nodes: ["guard", "approval_gate"], paused: true });
    wrap(<AgentGraph mermaid={SRC} />);
    expect(await screen.findByText("Last run: guard → approval_gate (waiting for approval)")).toBeInTheDocument();
  });
});

describe("AgentGraph thread picker", () => {
  it("lists only the selected world's threads, by title, kind and age, and leaves out empty chats", async () => {
    vi.setSystemTime(new Date("2026-11-13T12:00:00Z"));
    vi.mocked(getThreads).mockResolvedValue([
      summary("t1", "w", 0, { title: "How many moons does Velmar have?", created_at: "2026-11-13T11:39:00Z" }),
      summary("t2", "w", 0, { kind: "import", title: "Fan wiki: example.org (10 pages)", created_at: "2026-11-13T09:00:00Z" }),
      summary("t3", "w", 0, { title: null }), // an empty chat: nothing ran
      summary("t4", "other-world", 0, { title: "Elsewhere" }),
    ]);
    wrap(<AgentGraph mermaid={SRC} />);
    const select = (await screen.findByRole("combobox")) as HTMLSelectElement;
    await waitFor(() => expect(select.options).toHaveLength(2));
    expect([...select.options].map((o) => [o.value, o.text])).toEqual([
      ["t1", "How many moons does Velmar have? · chat · 21 min ago"],
      ["t2", "Fan wiki: example.org (10 pages) · import · 3 h ago"],
    ]);
    await waitFor(() => expect(getLastRun).toHaveBeenCalledWith("t1"));
    expect(getLastRun).not.toHaveBeenCalledWith("t4");
    vi.useRealTimers();
  });

  it("says when the world has no runs yet", async () => {
    vi.mocked(getThreads).mockResolvedValue([summary("t9", "other-world", 0)]);
    wrap(<AgentGraph mermaid={SRC} />);
    expect(await screen.findByRole("option", { name: "No threads in this world yet" })).toBeInTheDocument();
    expect(getLastRun).not.toHaveBeenCalled();
  });
});
