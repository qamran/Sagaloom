import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryPanel } from "@/components/MemoryPanel";
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
    wrap(<MemoryPanel />);
    expect(await screen.findByText(/3 threads/)).toBeInTheDocument();
    expect(screen.getByText("checkpoints.sqlite")).toBeInTheDocument();
    const invalidate = vi.spyOn(qc, "invalidateQueries");
    await userEvent.click(screen.getByRole("button", { name: "Delete tone: grim" }));
    expect(forgetMemory).toHaveBeenCalledWith("w", "tone", "grim");
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ["memory", "w"] }));
    await userEvent.click(screen.getByRole("button", { name: "Delete banned_tropes: amnesia" }));
    expect(forgetMemory).toHaveBeenCalledWith("w", "banned_tropes", "amnesia");
  });

  it("shows the count and cap, and singular thread wording", async () => {
    vi.mocked(getMemory).mockResolvedValue({
      ...payload({ tone: "grim" }, 1),
      short_term: { threads: 1, checkpoint_file: "c.sqlite" },
    });
    wrap(<MemoryPanel />);
    expect(await screen.findByText("Long-term preferences (1/20)")).toBeInTheDocument();
    expect(screen.getByText(/, 1 thread in/)).toBeInTheDocument();
  });

  it("leaves the thread count out when it is unknown", async () => {
    vi.mocked(getMemory).mockResolvedValue({
      ...payload({}),
      short_term: { threads: null, checkpoint_file: null },
    });
    wrap(<MemoryPanel />);
    expect(await screen.findByText("Short-term: a SQLite checkpointer")).toBeInTheDocument();
  });

  it("shows an alert when a Delete fails", async () => {
    vi.mocked(getMemory).mockResolvedValue(payload({ tone: "grim" }, 1));
    vi.mocked(forgetMemory).mockRejectedValue(new Error("down"));
    wrap(<MemoryPanel />);
    await userEvent.click(await screen.findByRole("button", { name: "Delete tone: grim" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The preference was not deleted");
  });

  it("says so when nothing is stored", async () => {
    vi.mocked(getMemory).mockResolvedValue(payload({}));
    wrap(<MemoryPanel />);
    expect(await screen.findByText('No preferences yet. Say "remember …" in chat.')).toBeInTheDocument();
  });

  it("Delete is busy while its request runs", async () => {
    vi.mocked(getMemory).mockResolvedValue(payload({ tone: "grim" }, 1));
    let release: (p: MemoryPayload) => void = () => {};
    vi.mocked(forgetMemory).mockReturnValue(new Promise((r) => (release = r)));
    wrap(<MemoryPanel />);
    const del = await screen.findByRole("button", { name: "Delete tone: grim" });
    await userEvent.click(del);
    expect(del).toBeDisabled();
    expect(del).toHaveAttribute("aria-busy", "true");
    release(payload({}));
    await waitFor(() => expect(del).toBeEnabled());
    expect(del).not.toHaveAttribute("aria-busy", "true");
  });

  it("each Delete stays busy until its own request ends", async () => {
    vi.mocked(getMemory).mockResolvedValue(payload({ tone: "grim", banned_tropes: ["amnesia"] }, 2));
    const releases: ((p: MemoryPayload) => void)[] = [];
    vi.mocked(forgetMemory).mockImplementation(() => new Promise((r) => releases.push(r)));
    wrap(<MemoryPanel />);
    const first = await screen.findByRole("button", { name: "Delete tone: grim" });
    const second = screen.getByRole("button", { name: "Delete banned_tropes: amnesia" });
    await userEvent.click(first);
    await userEvent.click(second);
    expect(first).toBeDisabled();
    expect(second).toBeDisabled();
    releases[0](payload({}));
    await waitFor(() => expect(first).toBeEnabled());
    expect(second).toBeDisabled();
    expect(second).toHaveAttribute("aria-busy", "true");
    releases[1](payload({}));
    await waitFor(() => expect(second).toBeEnabled());
  });
});
