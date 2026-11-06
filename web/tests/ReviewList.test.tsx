import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ReviewList } from "@/components/ReviewList";
import { getReviewThreads } from "@/lib/api";
import type { ThreadSummary } from "@/lib/types";

let world: { id: string; name: string } | null = { id: "w1", name: "Velmar" };
vi.mock("@/lib/world", () => ({
  useWorld: () => ({ world, isLoading: false, error: null }),
}));
vi.mock("@/lib/api", () => ({ getReviewThreads: vi.fn() }));

const row = (over: Partial<ThreadSummary>): ThreadSummary => ({
  thread_id: "t1", world_id: "w1", pending: 1, created_at: new Date().toISOString(), kind: "chat",
  title: "Sky of Velmar", badge: "conflict", ...over,
});
const renderList = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ReviewList />
    </QueryClientProvider>,
  );

beforeEach(() => {
  world = { id: "w1", name: "Velmar" };
  vi.mocked(getReviewThreads).mockReset();
});

describe("ReviewList", () => {
  it("renders a linked row per thread with its badge", async () => {
    vi.mocked(getReviewThreads).mockResolvedValue([
      row({}),
      row({ thread_id: "t2", title: "Salt Guild", pending: 3, badge: "retcon" }),
    ]);
    renderList();
    expect(screen.getByRole("heading", { level: 1, name: "Review" })).toBeInTheDocument();
    const first = await screen.findByRole("link", { name: /Sky of Velmar/ });
    expect(first).toHaveAttribute("href", "/review/t1");
    expect(within(first).getByText("Conflict")).toBeInTheDocument();
    expect(within(first).getByText("1 proposal")).toBeInTheDocument();
    expect(within(first).getByText("Chat")).toBeInTheDocument();
    const second = screen.getByRole("link", { name: /Salt Guild/ });
    expect(second).toHaveAttribute("href", "/review/t2");
    expect(within(second).getByText("Retcon")).toBeInTheDocument();
    expect(within(second).getByText("3 proposals")).toBeInTheDocument();
  });

  it("shows the empty state", async () => {
    vi.mocked(getReviewThreads).mockResolvedValue([]);
    renderList();
    expect(
      await screen.findByText("Nothing to review. Every change the assistant proposes waits here until you decide."),
    ).toBeInTheDocument();
  });

  it("shows Untitled chat for a null title", async () => {
    vi.mocked(getReviewThreads).mockResolvedValue([row({ title: null })]);
    renderList();
    expect(await screen.findByRole("link", { name: /Untitled chat/ })).toBeInTheDocument();
  });

  it("sits in a main landmark", async () => {
    vi.mocked(getReviewThreads).mockResolvedValue([]);
    renderList();
    expect(screen.getByRole("main")).toContainElement(screen.getByRole("heading", { level: 1, name: "Review" }));
    await screen.findByText(/Nothing to review/);
  });

  it("says so when no world is selected, not that the API failed", () => {
    world = null;
    renderList();
    expect(screen.getByText("No world selected.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
