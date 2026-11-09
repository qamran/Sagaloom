import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import NewChat from "@/app/chat/page";
import { ChatThread } from "@/components/ChatThread";
import { createThread, forgetMemory, getEntries, getLlmLog, getReviewThreads, getSettings, getThread } from "@/lib/api";
import { SHOW_SECRETS_KEY } from "@/lib/secrets";
import type { SettingsPayload, ThreadSummary } from "@/lib/types";

const summary = (thread_id: string, world_id: string, pending: number): ThreadSummary => ({
  thread_id, world_id, pending, created_at: "", kind: "chat", title: null, badge: null, approved: 0, rejected: 0, running: false,
});

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));
const active = vi.hoisted(() => ({ id: "w1" }));
vi.mock("@/lib/world", () => ({
  useWorld: () => ({
    world: { id: active.id, name: "Velmar", is_demo: true, divergent: false },
    isLoading: false,
    error: null,
    setThreadId: () => undefined,
  }),
}));
vi.mock("@/lib/api", () => ({
  createThread: vi.fn(),
  getReviewThreads: vi.fn(),
  getThread: vi.fn(),
  getEntries: vi.fn(async () => []),
  getLlmLog: vi.fn(async () => []),
  getSettings: vi.fn(),
  forgetMemory: vi.fn(),
}));

const settings = (guard_enabled: boolean): SettingsPayload => ({
  settings: { agent_temperature: 0, agent_max_tokens: null, agent_system_prompt: null, guard_enabled, enabled_tools: null },
  defaults: { agent_system_prompt: "x" },
  guard_policy: "p",
});

beforeEach(() => {
  vi.mocked(getSettings).mockReset().mockResolvedValue(settings(true));
  replace.mockReset();
  vi.mocked(createThread).mockReset().mockResolvedValue({ thread_id: "t_new" });
  vi.mocked(getReviewThreads).mockReset();
  vi.mocked(getLlmLog).mockReset().mockResolvedValue([]);
});

describe("/chat", () => {
  it("resumes a thread with a pending approval for the active world instead of creating one", async () => {
    vi.mocked(getReviewThreads).mockResolvedValue([
      summary("t_pending", "w1", 2),
      summary("t_older", "w1", 1),
    ]);
    render(<NewChat />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/chat/t_pending"));
    expect(getReviewThreads).toHaveBeenCalledWith("w1");
    expect(createThread).not.toHaveBeenCalled();
  });

  it("creates a thread when no pending one exists for the active world", async () => {
    vi.mocked(getReviewThreads).mockResolvedValue([]);
    render(<NewChat />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/chat/t_new"));
    expect(createThread).toHaveBeenCalledWith("w1");
  });

  it("still creates a thread when the pending lookup fails", async () => {
    vi.mocked(getReviewThreads).mockRejectedValue(new Error("down"));
    render(<NewChat />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/chat/t_new"));
  });
});

describe("/chat/[threadId]", () => {
  it("shows a blocked message's guard notice as a note", async () => {
    const copy = "That message tries to change how I work, so I didn't act on it.";
    vi.mocked(getThread).mockResolvedValue({
      thread_id: "t1",
      kind: "chat",
      title: null,
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
      kind: "chat",
      title: null,
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
      kind: "chat",
      title: null,
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
      kind: "chat",
      title: null,
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
  it("renders a memory message as a Remembered chip with Undo, a muted refusal and the course chip", async () => {
    vi.mocked(forgetMemory).mockReset().mockResolvedValue({} as never);
    renderThread([
      { role: "user", content: "Remember: keep the tone grim." },
      {
        role: "memory",
        content: "agent-facing: tone stored; notes refused",
        memory: [
          { key: "tone", value: "grim", stored: true, note: "Remembered: tone → grim" },
          { key: "notes", value: "zzz", stored: false, note: "Not remembered: it wasn't something the author said (notes: zzz)" },
        ],
      },
    ]);
    expect(await screen.findByText("Remembered: tone → grim")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /^Undo/ })).toHaveLength(1);
    expect(screen.getByText(/Not remembered: it wasn't something the author said/)).toBeInTheDocument();
    expect(screen.queryByText(/agent-facing/)).toBeNull();
    expect(screen.getByRole("link", { name: "Course note: Memory · store" })).toHaveAttribute(
      "href",
      "/studio?card=memory#feature-map",
    );
    await userEvent.click(screen.getByRole("button", { name: /^Undo/ }));
    expect(forgetMemory).toHaveBeenCalledWith("w1", "tone", "grim");
    expect(await screen.findByText("Forgotten")).toBeInTheDocument();
  });

  it("shows the router's mode as a course chip on a user message", async () => {
    renderThread([
      { role: "user", content: "How many moons?", mode: "query" },
      { role: "user", content: "No mode here" },
    ]);
    const chip = await screen.findByRole("link", { name: "Course note: Router · query" });
    expect(chip).toHaveAttribute("href", "/studio?card=router#feature-map");
    expect(screen.getAllByRole("link", { name: /Router/ })).toHaveLength(1);
    expect(screen.getByText("How many moons?")).toBeInTheDocument();
  });

  it("undoes in the thread's own world, not the selected one", async () => {
    vi.mocked(forgetMemory).mockReset().mockResolvedValue({} as never);
    vi.mocked(getThread).mockResolvedValue({
      thread_id: "t1",
      kind: "chat",
      title: null,
      world_id: "w_other",
      messages: [
        { role: "memory", content: "x", memory: [{ key: "tone", value: "grim", stored: true, note: "Remembered: tone → grim" }] },
      ],
      pending_interrupt: null,
      usage: { prompt_tokens: 0, completion_tokens: 0, cost_usd: 0 },
    } as never);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <ChatThread threadId="t1" />
      </QueryClientProvider>,
    );
    await userEvent.click(await screen.findByRole("button", { name: /Undo/ }));
    expect(forgetMemory).toHaveBeenCalledWith("w_other", "tone", "grim");
  });

  it("masks Under the hood by the thread's world: another world's toggle does not reveal it", async () => {
    sessionStorage.setItem(SHOW_SECRETS_KEY("w1"), "true"); // the active world's toggle is on
    vi.mocked(getThread).mockResolvedValue({
      thread_id: "t1",
      kind: "chat",
      title: null,
      world_id: "w2",
      messages: [{ role: "user", content: "hi" }],
      pending_interrupt: null,
      usage: { prompt_tokens: 0, completion_tokens: 0, cost_usd: 0 },
    } as never);
    vi.mocked(getLlmLog).mockResolvedValue([
      {
        id: "c1",
        thread_id: "t1",
        run_id: "r1",
        provider: "openrouter",
        model: "m",
        role: "judge",
        params: {},
        request: {
          messages: [
            { role: "user", content: '<untrusted_data source="ent_0003">\n- Sings: Yes [secret]\n</untrusted_data>' },
          ],
          tools: [],
        },
        response: null,
        started_at: "",
      },
    ]);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <ChatThread threadId="t1" />
      </QueryClientProvider>,
    );
    await screen.findByText("hi");
    await userEvent.click(screen.getByRole("button", { name: "Under the hood" }));
    const drawer = await screen.findByRole("complementary", { name: "Under the hood" });
    const wrapped = await within(drawer).findByTestId("untrusted");
    expect(wrapped).toHaveTextContent("[secret fact hidden]");
    expect(wrapped).not.toHaveTextContent("Sings: Yes");
    expect(within(drawer).getByRole("button", { name: "Show secrets" })).toHaveAttribute("aria-pressed", "false");
  });
});

describe("assistant entity chips", () => {
  const entry = (id: string, title: string, type: string, status = "canon", aliases: string[] = []) => ({
    id, title, type, status, aliases, world_id: "w1",
  });
  const mount = async (text: string) => {
    vi.mocked(getEntries).mockResolvedValue([
      entry("ent_0012", "Ister", "place", "canon", ["the red moon"]),
      entry("ent_0019", "The Choir Ledger", "item", "secret"),
    ] as never);
    vi.mocked(getThread).mockResolvedValue({
      thread_id: "t1", kind: "chat", title: null, world_id: "w1",
      messages: [{ role: "user", content: "ent_0012?" }, { role: "assistant", content: text }],
      pending_interrupt: null, usage: { prompt_tokens: 0, completion_tokens: 0, cost_usd: 0 },
    } as never);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={qc}><ChatThread threadId="t1" /></QueryClientProvider>);
  };

  it("renders entries named in assistant text as chips, but not in the author's message", async () => {
    await mount("Ister, the red moon (ent_0012)");
    const links = await screen.findAllByRole("link", { name: /place/ });
    expect(links.map((l) => l.getAttribute("href"))).toEqual(["/canon/ent_0012", "/canon/ent_0012", "/canon/ent_0012"]);
    expect(links.map((l) => l.textContent)).toEqual(["place Ister", "place the red moon", "place ent_0012"]);
    expect(screen.getByText("ent_0012?")).toBeInTheDocument(); // author text untouched
  });

  it("leaves a hidden secret entry as plain text", async () => {
    await mount("See ent_0019, the Choir Ledger.");
    await waitFor(() => expect(getEntries).toHaveBeenCalled());
    expect(await screen.findByText(/See ent_0019/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /item/ })).toBeNull();
  });

  it("chips the secret entry when the thread's world has secrets shown", async () => {
    sessionStorage.setItem(SHOW_SECRETS_KEY("w1"), "true");
    await mount("See ent_0019.");
    expect(await screen.findByRole("link", { name: /item/ })).toHaveAttribute("href", "/canon/ent_0019");
    sessionStorage.clear();
  });
  it("uses only the thread's world for chips and @ suggestions, not the active world", async () => {
    const e = (id: string, title: string, world_id: string, status: string) => ({
      id, title, type: "item", status, aliases: [], world_id,
    });
    vi.mocked(getEntries).mockImplementation((async (w: string) =>
      w === "w1"
        ? [e("ent_0001", "Plain Thing", "w1", "canon")]
        : [e("ent_0050", "Chalk Vault", "w2", "secret")]) as never);
    sessionStorage.setItem(SHOW_SECRETS_KEY("w1"), "true");
    sessionStorage.setItem(SHOW_SECRETS_KEY("w2"), "true");
    active.id = "w2";
    try {
      vi.mocked(getThread).mockResolvedValue({
        thread_id: "t1", kind: "chat", title: null, world_id: "w1",
        messages: [{ role: "assistant", content: "See ent_0050 and the Chalk Vault, and Plain Thing." }],
        pending_interrupt: null, usage: { prompt_tokens: 0, completion_tokens: 0, cost_usd: 0 },
      } as never);
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      render(<QueryClientProvider client={qc}><ChatThread threadId="t1" /></QueryClientProvider>);
      await screen.findByRole("link", { name: /Plain Thing/ });
      expect(screen.queryByRole("link", { name: /Chalk Vault|ent_0050/ })).toBeNull();
      await userEvent.type(screen.getByRole("combobox"), "@ch");
      expect(screen.queryByRole("listbox")).toBeNull();
    } finally {
      active.id = "w1";
      sessionStorage.clear();
    }
  });
});
