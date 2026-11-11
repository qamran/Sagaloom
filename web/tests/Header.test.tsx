import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Header } from "@/components/Header";
import { getMe, getReviewThreads } from "@/lib/api";
import { SHOW_SECRETS_KEY } from "@/lib/secrets";
import type { Me, ThreadSummary } from "@/lib/types";

vi.mock("next/navigation", () => ({ usePathname: () => "/canon", useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/world", () => ({
  useWorld: () => ({
    worlds: [], world: { id: "w1", name: "Velmar" }, threadId: null, setWorldId: vi.fn(), startWorld: vi.fn(),
  }),
}));
vi.mock("@/lib/api", () => ({ getThread: vi.fn(), getReviewThreads: vi.fn(), getMe: vi.fn() }));
const auth = vi.hoisted(() => ({ value: { isLoaded: true, isSignedIn: true } }));
vi.mock("@clerk/nextjs", () => ({ useAuth: () => auth.value, UserButton: () => <div data-testid="user-button" /> }));

const me = (over: Partial<Me> = {}): Me => ({
  id: "user_a", email: "a@b.c", display_name: "A", is_admin: false, last_world_id: null,
  month_spend_usd: 0.2345, monthly_budget_usd: 1, budget_resets_on: "2026-12-01", over_budget: false, ...over,
});

const row = (thread_id: string, pending: number): ThreadSummary => ({
  thread_id, world_id: "w1", pending, created_at: "", kind: "chat", title: null, badge: null, approved: 0, rejected: 0, running: false,
});
const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
const renderHeader = () =>
  render(
    <QueryClientProvider client={qc}>
      <Header />
    </QueryClientProvider>,
  );

beforeEach(() => {
  qc.clear();
  vi.mocked(getReviewThreads).mockReset().mockResolvedValue([]);
  vi.mocked(getMe).mockReset().mockResolvedValue(me());
  auth.value = { isLoaded: true, isSignedIn: true };
});

describe("Header Review tab", () => {
  it("shows the sum of pending proposals", async () => {
    vi.mocked(getReviewThreads).mockResolvedValue([row("t1", 2), row("t2", 1)]);
    renderHeader();
    const link = await screen.findByRole("link", { name: "Review 3 pending" });
    expect(link).toHaveAttribute("href", "/review");
    expect(getReviewThreads).toHaveBeenCalledWith("w1");
  });

  it("shows no pill when nothing is pending", async () => {
    vi.mocked(getReviewThreads).mockResolvedValue([]);
    renderHeader();
    await waitFor(() => expect(getReviewThreads).toHaveBeenCalledWith("w1"));
    // The fetch has resolved, and one more tick lets the query publish it to the DOM.
    await vi.mocked(getReviewThreads).mock.results[0].value;
    await act(async () => {});
    expect(await screen.findByRole("link", { name: "Review" })).toHaveTextContent(/^Review$/);
  });
});

describe("Header pill polling", () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => vi.useRealTimers());

  it("polls every 60 s when nothing runs", async () => {
    vi.mocked(getReviewThreads).mockResolvedValue([row("t1", 1)]);
    renderHeader();
    await screen.findByRole("link", { name: "Review 1 pending" });
    expect(getReviewThreads).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(15_000); });
    expect(getReviewThreads).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(45_000); });
    expect(getReviewThreads).toHaveBeenCalledTimes(2);
  });

  it("polls every 5 s while a thread runs", async () => {
    vi.mocked(getReviewThreads).mockResolvedValue([{ ...row("t1", 0), running: true }]);
    renderHeader();
    await waitFor(() => expect(getReviewThreads).toHaveBeenCalledTimes(1));
    await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
    expect(getReviewThreads).toHaveBeenCalledTimes(2);
  });

  it("pill updates after a decision without waiting for the interval", async () => {
    vi.mocked(getReviewThreads).mockResolvedValueOnce([row("t1", 2)]).mockResolvedValue([row("t1", 1)]);
    renderHeader();
    await screen.findByRole("link", { name: "Review 2 pending" });
    await act(async () => { await qc.invalidateQueries({ queryKey: ["review"] }); });
    expect(await screen.findByRole("link", { name: "Review 1 pending" })).toBeInTheDocument();
    expect(getReviewThreads).toHaveBeenCalledTimes(2);
  });
});

describe("Header Import tab", () => {
  it("links to /import after Review", async () => {
    vi.mocked(getReviewThreads).mockResolvedValue([]);
    renderHeader();
    const tabs = within(screen.getByRole("navigation", { name: "Main" })).getAllByRole("link");
    expect(tabs.map((t) => t.textContent)).toEqual(["Canon", "Chat", "Review", "Import"]);
    expect(screen.getByRole("link", { name: "Import" })).toHaveAttribute("href", "/import");
  });
});

describe("Header Show secrets toggle", () => {
  it("renders the toggle before Course notes, driving the world's state", async () => {
    vi.mocked(getReviewThreads).mockResolvedValue([]);
    renderHeader();
    const btn = screen.getByRole("button", { name: "Show secrets" });
    expect(btn).toHaveAttribute("aria-pressed", "false");
    expect(btn.compareDocumentPosition(screen.getByRole("button", { name: "Course notes" }))).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
    btn.click();
    await waitFor(() => expect(sessionStorage.getItem(SHOW_SECRETS_KEY("w1"))).toBe("true"));
    sessionStorage.clear();
  });
});

describe("Header account", () => {
  it("shows the spend line against the budget and the account menu", async () => {
    renderHeader();
    expect(await screen.findByLabelText("AI spend this month")).toHaveTextContent("This month: $0.23 of $1.00");
    expect(screen.getByTestId("user-button")).toBeInTheDocument();
  });

  it("shows only the spend for the admin, with no limit", async () => {
    vi.mocked(getMe).mockResolvedValue(me({ is_admin: true, monthly_budget_usd: null }));
    renderHeader();
    expect(await screen.findByLabelText("AI spend this month")).toHaveTextContent(/^This month: \$0\.23$/);
  });

  it("offers Sign in and Sign up free, and nothing else, when signed out", () => {
    auth.value = { isLoaded: true, isSignedIn: false };
    renderHeader();
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/sign-in");
    expect(screen.getByRole("link", { name: "Sign up free" })).toHaveAttribute("href", "/sign-up");
    expect(screen.queryByRole("navigation", { name: "Main" })).toBeNull();
    expect(screen.queryByTestId("user-button")).toBeNull();
    expect(getMe).not.toHaveBeenCalled();
  });
});
