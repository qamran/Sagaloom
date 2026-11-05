import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import NewChat from "@/app/chat/page";
import { ChatThread } from "@/components/ChatThread";
import { createThread, getPendingThreads, getSettings, getThread } from "@/lib/api";
import type { SettingsPayload } from "@/lib/types";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));
vi.mock("@/lib/world", () => ({
  useWorld: () => ({
    world: { id: "w1", name: "Velmar", is_demo: true, divergent: false },
    isLoading: false,
    error: null,
    setThreadId: () => undefined,
  }),
}));
vi.mock("@/lib/api", () => ({
  createThread: vi.fn(),
  getPendingThreads: vi.fn(),
  getThread: vi.fn(),
  getEntries: vi.fn(async () => []),
  getLlmLog: vi.fn(async () => []),
  getSettings: vi.fn(),
}));

const settings = (guard_enabled: boolean): SettingsPayload => ({
  settings: { agent_temperature: 0, agent_max_tokens: null, agent_system_prompt: null, guard_enabled },
  defaults: { agent_system_prompt: "x" },
  guard_policy: "p",
});

beforeEach(() => {
  vi.mocked(getSettings).mockReset().mockResolvedValue(settings(true));
  replace.mockReset();
  vi.mocked(createThread).mockReset().mockResolvedValue({ thread_id: "t_new" });
  vi.mocked(getPendingThreads).mockReset();
});

describe("/chat", () => {
  it("resumes a thread with a pending approval for the active world instead of creating one", async () => {
    vi.mocked(getPendingThreads).mockResolvedValue([
      { thread_id: "t_other", world_id: "w2", pending: 1 },
      { thread_id: "t_pending", world_id: "w1", pending: 1 },
    ]);
    render(<NewChat />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/chat/t_pending"));
    expect(createThread).not.toHaveBeenCalled();
  });

  it("creates a thread when no pending one exists for the active world", async () => {
    vi.mocked(getPendingThreads).mockResolvedValue([{ thread_id: "t_other", world_id: "w2", pending: 1 }]);
    render(<NewChat />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/chat/t_new"));
    expect(createThread).toHaveBeenCalledWith("w1");
  });

  it("still creates a thread when the pending lookup fails", async () => {
    vi.mocked(getPendingThreads).mockRejectedValue(new Error("down"));
    render(<NewChat />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/chat/t_new"));
  });
});

describe("/chat/[threadId]", () => {
  it("shows a blocked message's guard notice as a note", async () => {
    const copy = "That message tries to change how I work, so I didn't act on it.";
    vi.mocked(getThread).mockResolvedValue({
      thread_id: "t1",
      world_id: "w1",
      messages: [{ role: "guard", content: copy, name: "guard" }],
      pending_interrupt: null,
      usage: { prompt_tokens: 0, completion_tokens: 0, cost_usd: 0 },
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <ChatThread threadId="t1" />
      </QueryClientProvider>,
    );
    const note = await screen.findByRole("note", { name: "Blocked by the input guard" });
    expect(note).toHaveTextContent(copy);
  });

  it("shows a banner when the input guard is off, linking to Studio", async () => {
    vi.mocked(getSettings).mockResolvedValue(settings(false));
    vi.mocked(getThread).mockResolvedValue({
      thread_id: "t1",
      world_id: "w1",
      messages: [],
      pending_interrupt: null,
      usage: { prompt_tokens: 0, completion_tokens: 0, cost_usd: 0 },
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <ChatThread threadId="t1" />
      </QueryClientProvider>,
    );
    const banner = await screen.findByRole("status", { name: "Input guard status" });
    expect(banner).toHaveTextContent("Input guard off (Studio)");
    expect(screen.getByRole("link", { name: /Input guard off/ })).toHaveAttribute("href", "/studio#guardrails");
  });

  it("shows no banner while the guard is on", async () => {
    vi.mocked(getThread).mockResolvedValue({
      thread_id: "t1",
      world_id: "w1",
      messages: [],
      pending_interrupt: null,
      usage: { prompt_tokens: 0, completion_tokens: 0, cost_usd: 0 },
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <ChatThread threadId="t1" />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(getSettings).toHaveBeenCalled());
    expect(screen.queryByRole("status", { name: "Input guard status" })).toBeNull();
  });
  const renderThread = (messages: unknown[]) => {
    vi.mocked(getThread).mockResolvedValue({
      thread_id: "t1",
      world_id: "w1",
      messages,
      pending_interrupt: null,
      usage: { prompt_tokens: 0, completion_tokens: 0, cost_usd: 0 },
    } as never);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <ChatThread threadId="t1" />
      </QueryClientProvider>,
    );
  };

  it("annotates a blocked message with the Guardrail chip", async () => {
    renderThread([{ role: "guard", content: "blocked", name: "guard" }]);
    const note = await screen.findByRole("note", { name: "Blocked by the input guard" });
    expect(within(note).getByRole("link", { name: "Course note: Guardrail" })).toHaveAttribute(
      "href",
      "/studio?card=security_guard#feature-map",
    );
  });

  it("annotates a canon search with the Agentic RAG chip", async () => {
    renderThread([
      { role: "user", content: "hi" },
      { role: "assistant", content: "", tool_calls: [{ id: "c1", name: "search_canon", args: {} }] },
      { role: "assistant", content: "Done." },
    ]);
    expect(await screen.findByRole("link", { name: "Course note: Agentic RAG" })).toHaveAttribute(
      "href",
      "/studio?card=agentic_rag#feature-map",
    );
  });

  it("shows one Memory chip at the top of a restored thread", async () => {
    renderThread([
      { role: "user", content: "hi" },
      { role: "assistant", content: "Hello." },
    ]);
    const chip = await screen.findByRole("link", { name: "Course note: Memory · checkpointer" });
    expect(chip).toHaveAttribute("href", "/studio?card=memory#feature-map");
    expect(screen.getAllByRole("link", { name: /Memory/ })).toHaveLength(1);
  });

  it("shows no Memory chip on a brand-new thread", async () => {
    renderThread([]);
    await screen.findByRole("heading", { name: /Talk to/ });
    expect(screen.queryByRole("link", { name: /Memory/ })).toBeNull();
  });
});
