import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Dashboard } from "@/components/Dashboard";
import { getEntries, getReviewThreads, getThreads } from "@/lib/api";
import { canonHealth, credits, recentChats, resetDay, worldStats } from "@/lib/dashboard";
import { TOUR_KEYS } from "@/lib/tour";
import type { Entry, Me, ThreadSummary, World } from "@/lib/types";

vi.mock("next/navigation", () => ({ usePathname: () => "/home", useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/api", () => ({ getEntries: vi.fn(), getReviewThreads: vi.fn(), getThreads: vi.fn(), getMe: vi.fn() }));

const VELMAR: World = { id: "velmar", name: "Velmar", is_demo: true, divergent: false, owner_id: "user_a" };
const ASH: World = { id: "ash", name: "The Ashen Coast", is_demo: false, divergent: false, owner_id: "user_a" };

const world = vi.hoisted(() => ({
  value: {} as { world: World | null; worlds: World[]; isLoading: boolean; error: Error | null },
  setWorldId: vi.fn(),
  startWorld: vi.fn(),
}));
vi.mock("@/lib/world", () => ({
  useWorld: () => ({ ...world.value, setWorldId: world.setWorldId, startWorld: world.startWorld }),
}));
const meRef = vi.hoisted(() => ({ value: undefined as Me | undefined }));
vi.mock("@/lib/me", () => ({ useMe: () => meRef.value }));

const me = (over: Partial<Me> = {}): Me => ({
  id: "user_a", email: "a@b.c", display_name: "A", is_admin: false, last_world_id: null,
  month_spend_usd: 0.12, monthly_budget_usd: 1, budget_resets_on: "2026-12-01", over_budget: false, ...over,
});

const thread = (over: Partial<ThreadSummary>): ThreadSummary => ({
  thread_id: "t", world_id: "velmar", pending: 0, created_at: "2026-11-10T10:00:00Z", kind: "chat", title: null,
  badge: null, approved: 0, rejected: 0, running: false, ...over,
});

const entry = (over: Partial<Entry>): Entry =>
  ({
    id: "ent_0001", world_id: "velmar", title: "Lantern Quay", type: "place", status: "canon", aliases: [], body: "",
    facts: [], links: [], source: "official", source_url: null, sources: [], licence: null, trusted: true, version: 1,
    created_at: "2026-11-01T10:00:00Z", updated_at: "2026-11-01T10:00:00Z", ...over,
  }) as Entry;

const fact = (status: Entry["status"]) => ({ key: "k", value: "v", status, refs: [], told_by: null }) as Entry["facts"][number];

const ENTRIES = [
  entry({ id: "ent_0001", title: "Lantern Quay", created_at: "2026-11-01T10:00:00Z" }),
  entry({ id: "ent_0002", title: "The Song of Three Moons", type: "event", status: "myth", created_at: "2026-11-03T10:00:00Z" }),
  entry({ id: "ent_0003", title: "The Choir Ledger", type: "item", status: "secret", created_at: "2026-11-05T10:00:00Z" }),
  entry({ id: "ent_0004", title: "Mayor Elsbeth Varr", type: "character", facts: [fact("secret"), fact("rumour")] }),
];

const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
const renderDashboard = () =>
  render(
    <QueryClientProvider client={qc}>
      <Dashboard />
    </QueryClientProvider>,
  );

beforeEach(() => {
  qc.clear();
  world.value = { world: VELMAR, worlds: [VELMAR, ASH], isLoading: false, error: null };
  world.setWorldId.mockReset();
  world.startWorld.mockReset().mockResolvedValue(ASH);
  meRef.value = me();
  vi.mocked(getEntries).mockReset().mockResolvedValue(ENTRIES);
  vi.mocked(getThreads).mockReset().mockResolvedValue([
    thread({ thread_id: "c1", title: "How many moons?", created_at: "2026-11-09T10:00:00Z" }),
    thread({ thread_id: "c2", title: "Festivals of Lantern Quay", created_at: "2026-11-11T10:00:00Z", pending: 1, badge: "conflict" }),
    thread({ thread_id: "i1", kind: "import", title: "Harbour notes", pending: 2 }),
    thread({ thread_id: "a1", world_id: "ash", title: "Ash chat" }),
    thread({ thread_id: "e1", title: null, created_at: "2026-11-12T10:00:00Z" }), // empty: never shown
  ]);
  vi.mocked(getReviewThreads).mockReset().mockResolvedValue([
    thread({ thread_id: "c2", title: "Festivals of Lantern Quay", pending: 1, badge: "conflict" }),
    thread({ thread_id: "i1", kind: "import", title: "Harbour notes", pending: 2, badge: null }),
  ]);
});

describe("Dashboard", () => {
  it("lists what needs a decision, linking each to its review, with the total waiting", async () => {
    renderDashboard();
    const panel = within(screen.getByRole("region", { name: /Needs your decision/ }));
    const conflict = await panel.findByRole("link", { name: /Festivals of Lantern Quay/ });
    expect(conflict).toHaveAttribute("href", "/review/c2");
    expect(conflict).toHaveTextContent("Conflict");
    // A row with no badge shows none: never "No conflicts" for an unknown check.
    const imp = panel.getByRole("link", { name: /Harbour notes/ });
    expect(imp).toHaveTextContent("Import · 2 proposals");
    expect(imp).not.toHaveTextContent(/No conflicts|Clear/);
    expect(screen.getByRole("heading", { name: /^Needs your decision\s*3$/ })).toBeInTheDocument();
  });

  it("says nothing is waiting only once the queue has loaded empty", async () => {
    vi.mocked(getReviewThreads).mockResolvedValue([]);
    renderDashboard();
    expect(await screen.findByText(/Nothing waiting\./)).toBeInTheDocument();
  });

  it("shows each world with its chats and waiting proposals, and switches world on click", async () => {
    renderDashboard();
    const panel = within(screen.getByRole("region", { name: "My worlds" }));
    const velmar = panel.getByRole("button", { name: /^Velmar/ });
    expect(velmar).toHaveAttribute("aria-current", "true");
    await waitFor(() => expect(velmar).toHaveTextContent("4 entries · 2 chats · 3 waiting"));
    expect(velmar).toHaveTextContent(/SAMPLE.*CURRENT/);
    await userEvent.click(panel.getByRole("button", { name: /The Ashen Coast/ }));
    expect(world.setWorldId).toHaveBeenCalledWith("ash");
  });

  it("creates a new world from its name", async () => {
    renderDashboard();
    await userEvent.click(screen.getByRole("button", { name: "+ New world" }));
    await userEvent.type(screen.getByLabelText("New world name"), "Isle of Rook");
    await userEvent.click(screen.getByRole("button", { name: "Create" }));
    expect(world.startWorld).toHaveBeenCalledWith("Isle of Rook");
  });

  it("counts canon health over entries and facts, and hides secret titles in Recently added", async () => {
    renderDashboard();
    const health = within(screen.getByRole("region", { name: "Canon health" }));
    expect(await health.findByText("4")).toBeInTheDocument(); // entries
    // Each tile opens Canon filtered to what it counts.
    expect(health.getByRole("link", { name: /entries/ })).toHaveAttribute("href", "/canon");
    expect(health.getByRole("link", { name: "1 myth" })).toHaveAttribute("href", "/canon?status=myth");
    expect(health.getByRole("link", { name: "1 rumour" })).toHaveAttribute("href", "/canon?status=rumour");
    expect(health.getByRole("link", { name: /secrets/ })).toHaveAttribute("href", "/canon?status=secret");
    const recent = await screen.findAllByRole("link", { name: /ago|just now|d ago/ });
    expect(recent.length).toBeGreaterThan(0);
    expect(screen.getByText("Hidden secret entry")).toBeInTheDocument();
    expect(screen.queryByText("The Choir Ledger")).toBeNull();
  });

  it("shows this world's chats only, newest first, not imports", async () => {
    renderDashboard();
    const links = await screen.findAllByRole("link", { name: /How many moons\?|Festivals of Lantern Quay ·/ });
    expect(links.map((l) => l.getAttribute("href"))).toEqual(["/chat/c2", "/chat/c1"]);
    expect(screen.queryByRole("link", { name: /Ash chat/ })).toBeNull();
    expect(screen.queryByRole("link", { name: /Untitled chat/ })).toBeNull();
  });

  it("shows credits left of the budget, with the reset day", async () => {
    renderDashboard();
    const box = within(screen.getByRole("region", { name: "AI credits this month" }));
    expect(box.getByText("$0.88")).toBeInTheDocument();
    expect(box.getByText(/left of \$1\.00 · \$0\.12 used/)).toBeInTheDocument();
    expect(box.getByText("resets 1 Dec")).toBeInTheDocument();
    expect(box.getByRole("progressbar", { name: "AI budget used" })).toHaveAttribute("aria-valuenow", "12");
  });

  it("shows unlimited credits for the admin, with no bar", () => {
    meRef.value = me({ is_admin: true, monthly_budget_usd: null, month_spend_usd: 0.42 });
    renderDashboard();
    const box = within(screen.getByRole("region", { name: "AI credits this month" }));
    expect(box.getByText("Unlimited")).toBeInTheDocument();
    expect(box.getByText(/\$0\.42 used this month \(admin\)/)).toBeInTheDocument();
    expect(box.queryByRole("progressbar")).toBeNull();
  });

  it("shows the Get Started cards on the demo world until hidden, marking the next step", async () => {
    localStorage.setItem(TOUR_KEYS.visited, "1");
    renderDashboard();
    const start = within(await screen.findByRole("region", { name: "Get started" }));
    expect(start.getByText("1 of 4 done ·", { exact: false })).toBeInTheDocument();
    expect(start.getByRole("link", { name: /Ask your canon.*Next/ })).toHaveAttribute(
      "href",
      `/chat?prompt=${encodeURIComponent("How many moons does Velmar have?")}`,
    );
    await userEvent.click(start.getByRole("button", { name: "Hide" }));
    expect(screen.queryByRole("region", { name: "Get started" })).toBeNull();
  });

  it("leaves out Get Started on a world of the author's own", () => {
    world.value = { ...world.value, world: ASH };
    renderDashboard();
    expect(screen.queryByRole("region", { name: "Get started" })).toBeNull();
  });

  it("waits for the worlds before showing panels", () => {
    world.value = { world: null, worlds: [], isLoading: true, error: null };
    renderDashboard();
    expect(screen.getByText("Loading your worlds…")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: /Needs your decision/ })).toBeNull();
  });
});

describe("dashboard numbers", () => {
  it("adds up chats and waiting proposals per world", () => {
    const s = worldStats([
      thread({ title: "Moons?", pending: 2 }),
      thread({ kind: "import", pending: 1 }),
      thread({ title: null }), // an empty chat is not counted
      thread({ world_id: "ash", title: "Ash" }),
    ]);
    expect(s.get("velmar")).toEqual({ chats: 1, waiting: 3 });
    expect(s.get("ash")).toEqual({ chats: 1, waiting: 0 });
  });

  it("counts the entries that are, or hold a fact that is, a myth, rumour or secret", () => {
    expect(canonHealth(ENTRIES)).toEqual({ entries: 4, myths: 1, rumours: 1, secrets: 2 });
  });

  it("counts an entry once, however many of its facts share the status", () => {
    const song = entry({ id: "ent_0009", status: "myth", facts: [fact("myth"), fact("myth")] });
    expect(canonHealth([song])).toMatchObject({ entries: 1, myths: 1 });
  });

  it("keeps only chats of one world, newest first", () => {
    const rows = recentChats(
      [thread({ thread_id: "old", title: "a", created_at: "2026-01-01T00:00:00Z" }), thread({ thread_id: "new", title: "b", created_at: "2026-02-01T00:00:00Z" }), thread({ thread_id: "imp", kind: "import", title: "c" })],
      "velmar",
    );
    expect(rows.map((r) => r.thread_id)).toEqual(["new", "old"]);
  });

  it("leaves out chats with no messages, but keeps one whose first turn is running", () => {
    const rows = recentChats(
      [thread({ thread_id: "empty", title: null }), thread({ thread_id: "busy", title: null, running: true }), thread({ thread_id: "said", title: "Hi" })],
      "velmar",
    );
    expect(rows.map((r) => r.thread_id).sort()).toEqual(["busy", "said"]);
  });

  it("never shows less than nothing left, and marks an empty budget as used up", () => {
    expect(credits(me({ month_spend_usd: 1.3, over_budget: true }))).toMatchObject({ headline: "$0.00", usedPercent: 100, over: true });
    expect(credits(me({ monthly_budget_usd: 0, month_spend_usd: 0 }))).toMatchObject({ headline: "$0.00", usedPercent: 100 });
  });

  it("formats the reset day as a UTC date", () => {
    expect(resetDay("2026-12-01")).toBe("1 Dec");
    expect(resetDay("not a date")).toBe("not a date");
  });
});
