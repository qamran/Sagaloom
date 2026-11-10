import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RememberedChip } from "@/components/RememberedChip";
import { forgetMemory } from "@/lib/api";
import type { MemoryPayload } from "@/lib/types";

vi.mock("@/lib/api", () => ({ forgetMemory: vi.fn() }));

const payload = (preferences: MemoryPayload["preferences"]): MemoryPayload => ({
  preferences,
  count: 0,
  cap: 20,
  short_term: { threads: 3, checkpoint_file: "checkpoints.sqlite" },
});

let qc: QueryClient;
const wrap = (ui: React.ReactNode) => {
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
};

beforeEach(() => {
  vi.mocked(forgetMemory).mockReset().mockResolvedValue(payload({}));
});

describe("RememberedChip", () => {
  const stored = { key: "tone", value: "grim", stored: true, note: "Remembered: tone → grim" };

  it("Undo forgets the key and the chip reads Forgotten", async () => {
    wrap(<RememberedChip worldId="w" result={stored} />);
    await userEvent.click(screen.getByRole("button", { name: /^Undo/ }));
    expect(forgetMemory).toHaveBeenCalledWith("w", "tone", "grim");
    expect(await screen.findByRole("status")).toHaveTextContent("Forgotten");
  });

  it("a stale Undo says Already changed", async () => {
    vi.mocked(forgetMemory).mockResolvedValue(payload({ tone: "wry" }));
    wrap(<RememberedChip worldId="w" result={stored} />);
    await userEvent.click(screen.getByRole("button", { name: /^Undo/ }));
    expect(await screen.findByRole("status")).toHaveTextContent("Already changed");
    expect(screen.queryByText("Forgotten")).toBeNull();
  });

  it("Undo invalidates the memory query", async () => {
    wrap(<RememberedChip worldId="w" result={stored} />);
    const invalidate = vi.spyOn(qc, "invalidateQueries");
    await userEvent.click(screen.getByRole("button", { name: "Undo Remembered: tone → grim" }));
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ["memory", "w"] }));
  });

  it("shows an alert when Undo fails and keeps the button", async () => {
    vi.mocked(forgetMemory).mockRejectedValue(new Error("down"));
    wrap(<RememberedChip worldId="w" result={stored} />);
    await userEvent.click(screen.getByRole("button", { name: "Undo Remembered: tone → grim" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not undo");
    expect(screen.getByRole("button", { name: /Undo/ })).toBeEnabled();
  });

  it("Undo of a list key passes the item", async () => {
    const r = { key: "notes", value: "no gods", stored: true, note: "Remembered: notes → no gods" };
    wrap(<RememberedChip worldId="w" result={r} />);
    await userEvent.click(screen.getByRole("button", { name: /^Undo/ }));
    expect(forgetMemory).toHaveBeenCalledWith("w", "notes", "no gods");
  });

  it("shows a refused result as plain text from its note", () => {
    const r = { key: "tone", value: "x", stored: false, note: "Not remembered: memory is full (20 preferences) (tone: x)" };
    wrap(<RememberedChip worldId="w" result={r} />);
    expect(screen.getByText(r.note)).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });
});
