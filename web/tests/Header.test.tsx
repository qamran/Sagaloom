import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Header } from "@/components/Header";
import { getReviewThreads } from "@/lib/api";
import { SHOW_SECRETS_KEY } from "@/lib/secrets";
import type { ThreadSummary } from "@/lib/types";

vi.mock("next/navigation", () => ({ usePathname: () => "/canon", useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/world", () => ({
  useWorld: () => ({
    worlds: [], world: { id: "w1", name: "Velmar" }, threadId: null, setWorldId: vi.fn(), startWorld: vi.fn(),
  }),
}));
vi.mock("@/lib/api", () => ({ getThread: vi.fn(), getReviewThreads: vi.fn() }));

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
  vi.mocked(getReviewThreads).mockReset();
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
    expect(await screen.findByRole("link", { name: "Review" })).toHaveTextContent(/^Review$/);
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
