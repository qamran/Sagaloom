import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import NewChat from "@/app/chat/page";
import { createThread, getPendingThreads } from "@/lib/api";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));
vi.mock("@/lib/world", () => ({
  useWorld: () => ({
    world: { id: "w1", name: "Velmar", is_demo: true, divergent: false },
    isLoading: false,
    error: null,
  }),
}));
vi.mock("@/lib/api", () => ({ createThread: vi.fn(), getPendingThreads: vi.fn() }));

beforeEach(() => {
  replace.mockReset();
  vi.mocked(createThread).mockReset().mockResolvedValue({ thread_id: "t_new" });
  vi.mocked(getPendingThreads).mockReset();
});

describe("/chat", () => {
  it("resumes a thread with a pending approval for the active world instead of creating one", async () => {
    vi.mocked(getPendingThreads).mockResolvedValue([
      { thread_id: "t_other", world_id: "w2", pending: 1 },
      { thread_id: "t_pending", world_id: "w1", pending: 1 },
    ]);
    render(<NewChat />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/chat/t_pending"));
    expect(createThread).not.toHaveBeenCalled();
  });

  it("creates a thread when no pending one exists for the active world", async () => {
    vi.mocked(getPendingThreads).mockResolvedValue([{ thread_id: "t_other", world_id: "w2", pending: 1 }]);
    render(<NewChat />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/chat/t_new"));
    expect(createThread).toHaveBeenCalledWith("w1");
  });

  it("still creates a thread when the pending lookup fails", async () => {
    vi.mocked(getPendingThreads).mockRejectedValue(new Error("down"));
    render(<NewChat />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/chat/t_new"));
  });
});
