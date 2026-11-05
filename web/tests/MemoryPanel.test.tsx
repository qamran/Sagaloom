import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryPanel } from "@/components/MemoryPanel";
import { RememberedChip } from "@/components/RememberedChip";
import { forgetMemory, getMemory } from "@/lib/api";
import type { MemoryPayload } from "@/lib/types";

vi.mock("@/lib/api", () => ({ getMemory: vi.fn(), forgetMemory: vi.fn() }));
vi.mock("@/lib/world", () => ({ useWorld: () => ({ world: { id: "w" } }) }));

const payload = (preferences: MemoryPayload["preferences"], count = 0): MemoryPayload => ({
  preferences,
  count,
  cap: 20,
  short_term: { threads: 3, checkpoint_file: "checkpoints.sqlite" },
});

let qc: QueryClient;
const wrap = (ui: React.ReactNode) => {
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
};

beforeEach(() => {
  vi.mocked(getMemory).mockReset();
  vi.mocked(forgetMemory).mockReset().mockResolvedValue(payload({}));
});

describe("MemoryPanel", () => {
  it("shows the short-term stats and each preference with a Delete", async () => {
    vi.mocked(getMemory).mockResolvedValue(
      payload({ tone: "grim", banned_tropes: ["chosen-one prophecies", "amnesia"] }, 3),
    );
    wrap(<MemoryPanel worldId="w" />);
    expect(await screen.findByText(/3 threads/)).toBeInTheDocument();
    expect(screen.getByText("checkpoints.sqlite")).toBeInTheDocument();
    const invalidate = vi.spyOn(qc, "invalidateQueries");
    await userEvent.click(screen.getByRole("button", { name: "Delete tone: grim" }));
    expect(forgetMemory).toHaveBeenCalledWith("w", "tone", undefined);
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ["memory", "w"] }));
    await userEvent.click(screen.getByRole("button", { name: "Delete banned_tropes: amnesia" }));
    expect(forgetMemory).toHaveBeenCalledWith("w", "banned_tropes", "amnesia");
  });

  it("says so when nothing is stored", async () => {
    vi.mocked(getMemory).mockResolvedValue(payload({}));
    wrap(<MemoryPanel worldId="w" />);
    expect(await screen.findByText('No preferences yet. Say "remember …" in chat.')).toBeInTheDocument();
  });
});

describe("RememberedChip", () => {
  const stored = { key: "tone", value: "grim", stored: true, note: "Remembered: tone → grim" };

  it("Undo forgets the key and the chip reads Forgotten", async () => {
    wrap(<RememberedChip worldId="w" result={stored} />);
    await userEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(forgetMemory).toHaveBeenCalledWith("w", "tone", undefined);
    expect(await screen.findByText("Forgotten")).toBeInTheDocument();
  });

  it("Undo of a list key passes the item", async () => {
    const r = { key: "notes", value: "no gods", stored: true, note: "Remembered: notes → no gods" };
    wrap(<RememberedChip worldId="w" result={r} />);
    await userEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(forgetMemory).toHaveBeenCalledWith("w", "notes", "no gods");
  });

  it("shows a refused result as plain text from its note", () => {
    const r = { key: "tone", value: "x", stored: false, note: "Not remembered: memory is full (20 preferences) (tone: x)" };
    wrap(<RememberedChip worldId="w" result={r} />);
    expect(screen.getByText(r.note)).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });
});
