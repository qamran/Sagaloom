import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useImport } from "@/lib/useImport";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const sse = (event: string, data: unknown) => `event: ${event}\r\ndata: ${JSON.stringify(data)}\r\n\r\n`;
function streamResponse(chunks: string[], gate?: Promise<void>) {
  const enc = new TextEncoder();
  let i = 0;
  return {
    ok: true,
    status: 200,
    json: async () => ({}),
    body: {
      getReader: () => ({
        read: async () => {
          if (i < chunks.length) {
            if (i === 2 && gate) await gate;
            return { done: false, value: enc.encode(chunks[i++]) };
          }
          return { done: true, value: undefined };
        },
      }),
    },
  };
}
const errorResponse = (status: number, detail?: string) => ({
  ok: false, status, body: null, json: async () => (detail ? { detail } : {}),
});

let fetchMock: ReturnType<typeof vi.fn>;
let qc: QueryClient;
const setup = () => {
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  return renderHook(() => useImport(), { wrapper });
};

beforeEach(() => {
  push.mockReset();
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

describe("useImport", () => {
  it("reports the candidates while extracting, then sends the body", async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    fetchMock.mockResolvedValue(
      streamResponse(
        [
          sse("node", { name: "extract", phase: "start" }),
          sse("tool_result", { name: "extract", summary: "2 candidates, 1 not imported", candidates: 2, skipped: 1 }),
          sse("node", { name: "check", phase: "start" }),
          sse("done", { thread_id: "t1" }),
        ],
        gate,
      ),
    );
    const { result } = setup();
    let p!: Promise<void>;
    act(() => {
      p = result.current.start("w1", { text: "Some notes", filename: "a.md" });
    });
    await waitFor(() => expect(result.current.candidates).toBe(2));
    expect(result.current.phase).toBe("extracting");
    expect(result.current.skipped).toBe(1);
    expect(result.current.worldId).toBe("w1"); // the drawer's secrets follow the import's world
    release();
    await act(async () => {
      await p;
    });
    expect(result.current.events.map((e) => e.event)).toContain("node");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/proxy/worlds/w1/imports",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ text: "Some notes", filename: "a.md" }) }),
    );
  });

  it("reaches checking on the check node, and done opens the review", async () => {
    fetchMock.mockResolvedValue(
      streamResponse([sse("node", { name: "check", phase: "start" }), sse("done", { thread_id: "t1" })]),
    );
    const invalidate = vi.spyOn(qc, "invalidateQueries");
    const { result } = setup();
    await act(async () => {
      await result.current.start("w1", { text: "x" });
    });
    expect(result.current.phase).toBe("checking");
    expect(push).toHaveBeenCalledWith("/review/t1");
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["review"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["imports"] });
  });

  it("shows an error event's message and stays on the page", async () => {
    const message = "The extraction could not run, so nothing was imported. Try again.";
    fetchMock.mockResolvedValue(streamResponse([sse("error", { message, retryable: true })]));
    const { result } = setup();
    await act(async () => {
      await result.current.start("w1", { text: "x" });
    });
    expect(result.current.phase).toBe("error");
    expect(result.current.error).toBe(message);
    expect(push).not.toHaveBeenCalled();
  });

  it.each([
    [413, undefined, "That text is too large."],
    [429, undefined, "Too many requests. Wait a moment and try again."],
    [422, "Paste or upload some text first.", "Paste or upload some text first."],
  ])("maps %i to its copy", async (status, detail, copy) => {
    fetchMock.mockResolvedValue(errorResponse(status, detail));
    const { result } = setup();
    await act(async () => {
      await result.current.start("w1", { text: "x" });
    });
    expect(result.current.phase).toBe("error");
    expect(result.current.error).toBe(copy);
  });
});
