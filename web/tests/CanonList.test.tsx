import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { CanonList } from "@/components/CanonList";
import type { Entry } from "@/lib/types";

vi.mock("next/navigation", () => ({ usePathname: () => "/canon" }));
vi.mock("@/lib/world", () => ({
  useWorld: () => ({ world: { id: "w1", name: "Velmar", is_demo: true, divergent: false } }),
}));

const base = {
  world_id: "w1", body: "", source: "user", source_url: null, licence: null, trusted: true,
  aliases: [], links: [], facts: [], version: 1, created_at: "", updated_at: "",
} as const;
const entries = [
  { ...base, id: "ent_0001", title: "Sky of Velmar", type: "place", status: "canon" },
  { ...base, id: "ent_0002", title: "The Mayor's Oath", type: "event", status: "secret" },
] as unknown as Entry[];

vi.mock("@/lib/api", () => ({ getEntries: vi.fn(async () => entries) }));

function renderList() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <CanonList />
    </QueryClientProvider>,
  );
}

describe("CanonList secrets", () => {
  it("does not let search reveal or count-filter secret entries until shown", async () => {
    renderList();
    await screen.findByText("Sky of Velmar");
    expect(screen.queryByText(/Mayor/)).toBeNull();
    expect(screen.getByRole("button", { name: "Show 1 secret entry" })).toBeInTheDocument();

    // A query matching only the secret title: no results, and the hidden count is unchanged.
    await userEvent.type(screen.getByLabelText("Search entries"), "Mayor");
    expect(screen.getByText("No entries match.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show 1 secret entry" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Show 1 secret entry" }));
    expect(screen.getByText(/Mayor/)).toBeInTheDocument();
  });
});
