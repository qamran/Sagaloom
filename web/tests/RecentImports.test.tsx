import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RecentImports } from "@/components/RecentImports";
import { getImports } from "@/lib/api";
import type { ThreadSummary } from "@/lib/types";

vi.mock("@/lib/world", () => ({ useWorld: () => ({ world: { id: "w1", name: "Velmar" } }) }));
vi.mock("@/lib/api", () => ({ getImports: vi.fn() }));

const row = (over: Partial<ThreadSummary>): ThreadSummary => ({
  thread_id: "t1", world_id: "w1", pending: 2, created_at: new Date().toISOString(), kind: "import",
  title: "notes.md", badge: null, approved: 1, rejected: 0, running: false, ...over,
});
const renderIt = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <RecentImports />
    </QueryClientProvider>,
  );

beforeEach(() => vi.mocked(getImports).mockReset());

describe("RecentImports", () => {
  it("shows title, age and decided counts, linked to Review", async () => {
    vi.mocked(getImports).mockResolvedValue([row({})]);
    renderIt();
    const link = await screen.findByRole("link", { name: /notes\.md/ });
    expect(link).toHaveAttribute("href", "/review/t1");
    expect(link).toHaveTextContent("just now");
    expect(link).toHaveTextContent("2 pending · 1 approved · 0 rejected");
    expect(getImports).toHaveBeenCalledWith("w1");
  });

  it("shows Importing… for a running import", async () => {
    vi.mocked(getImports).mockResolvedValue([row({ running: true })]);
    renderIt();
    expect(await screen.findByText("Importing…")).toBeInTheDocument();
    expect(screen.queryByText(/pending/)).toBeNull();
    // Still extracting: there is nothing to review yet, so the row is not a link.
    expect(screen.getByText("notes.md")).toBeInTheDocument();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("falls back to Untitled import", async () => {
    vi.mocked(getImports).mockResolvedValue([row({ title: null })]);
    renderIt();
    expect(await screen.findByRole("link", { name: /Untitled import/ })).toBeInTheDocument();
  });
});
