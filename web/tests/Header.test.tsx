import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Header } from "@/components/Header";
import { getReviewThreads } from "@/lib/api";
import type { ThreadSummary } from "@/lib/types";

vi.mock("next/navigation", () => ({ usePathname: () => "/canon", useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/world", () => ({
  useWorld: () => ({
    worlds: [], world: { id: "w1", name: "Velmar" }, threadId: null, setWorldId: vi.fn(), startWorld: vi.fn(),
  }),
}));
vi.mock("@/lib/api", () => ({ getThread: vi.fn(), getReviewThreads: vi.fn() }));

const row = (thread_id: string, pending: number): ThreadSummary => ({
  thread_id, world_id: "w1", pending, created_at: "", kind: "chat", title: null, badge: null,
});
const renderHeader = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Header />
    </QueryClientProvider>,
  );

beforeEach(() => vi.mocked(getReviewThreads).mockReset());

describe("Header Review tab", () => {
  it("shows the sum of pending proposals", async () => {
    vi.mocked(getReviewThreads).mockResolvedValue([row("t1", 2), row("t2", 1)]);
    renderHeader();
    const link = await screen.findByRole("link", { name: "Review 3" });
    expect(link).toHaveAttribute("href", "/review");
    expect(getReviewThreads).toHaveBeenCalledWith("w1");
  });

  it("shows no pill when nothing is pending", async () => {
    vi.mocked(getReviewThreads).mockResolvedValue([]);
    renderHeader();
    await vi.waitFor(() => expect(getReviewThreads).toHaveBeenCalled());
    expect(screen.getByRole("link", { name: "Review" })).toHaveTextContent(/^Review$/);
  });
});
