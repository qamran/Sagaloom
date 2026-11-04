import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getThread } from "@/lib/api";
import { TOUR_KEYS } from "@/lib/tour";
import type { CheckResult, PendingInterrupt, Proposal, ThreadState } from "@/lib/types";
import { useAgentStream } from "@/lib/useAgentStream";

vi.mock("@/lib/api", () => ({ getThread: vi.fn() }));
const getThreadMock = vi.mocked(getThread);

const usage = (cost: number) => ({ prompt_tokens: 10, completion_tokens: 5, cost_usd: cost });

const proposal = (id: string): Proposal => ({
  proposal_id: id, action: "create", world_id: "w1", entry_id: null, before: null,
  after: { title: `Entry ${id}`, type: "place", body: "", status: "canon", aliases: [], facts: [] },
});
const clean = (id: string): CheckResult => ({ proposal_id: id, verdict: "none", flags: [], dependents: [] });
const pendingOf = (...ids: string[]): PendingInterrupt => ({
  proposals: ids.map(proposal),
  checks: Object.fromEntries(ids.map((id) => [id, clean(id)])),
});

const thread = (over: Partial<ThreadState> = {}): ThreadState => ({
  thread_id: "t1", world_id: "w1", messages: [], pending_interrupt: null, usage: usage(0), ...over,
});

const sse = (event: string, data: unknown) => `event: ${event}\r\ndata: ${JSON.stringify(data)}\r\n\r\n`;

/** A fetch Response stand-in whose body yields `chunks`, then closes or drops the connection. */
function streamResponse(chunks: string[], end: "close" | "drop" = "close") {
  const enc = new TextEncoder();
  let i = 0;
  return {
    ok: true,
    status: 200,
    json: async () => ({}),
    body: {
      getReader: () => ({
        read: async () => {
          if (i < chunks.length) return { done: false, value: enc.encode(chunks[i++]) };
          if (end === "drop") throw new TypeError("network error");
          return { done: true, value: undefined };
        },
        cancel: async () => undefined,
        releaseLock: () => undefined,
      }),
    },
  };
}

const errorResponse = (status: number, detail: string) => ({
  ok: false, status, body: null, json: async () => ({ detail }),
});

let fetchMock: ReturnType<typeof vi.fn>;
let qc: QueryClient;

function setup() {
  const statuses: string[] = [];
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  const hook = renderHook(
    () => {
      const s = useAgentStream("t1");
      if (statuses[statuses.length - 1] !== s.status) statuses.push(s.status);
      return s;
    },
    { wrapper },
  );
  return { ...hook, statuses };
}

function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

const bodyOf = (call: unknown[]) => JSON.parse((call[1] as RequestInit).body as string);

beforeEach(() => {
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  getThreadMock.mockReset();
});
afterEach(() => vi.unstubAllGlobals());

describe("useAgentStream", () => {
  it("useAgentStream restores pending from getThread on mount", async () => {
    getThreadMock.mockResolvedValue(
      thread({
        messages: [{ role: "user", content: "Add three moons" }],
        pending_interrupt: pendingOf("p_1"),
        usage: usage(0.0031),
      }),
    );
    const { result } = setup();
    await waitFor(() => expect(result.current.pending?.proposals[0].proposal_id).toBe("p_1"));
    expect(result.current.messages).toEqual([{ role: "user", content: "Add three moons" }]);
    expect(result.current.usage?.cost_usd).toBe(0.0031);
    expect(getThreadMock).toHaveBeenCalledWith("t1");
    expect(result.current.status).toBe("idle");
  });

  it("useAgentStream goes reconnecting then recovers when the stream errors", async () => {
    getThreadMock.mockResolvedValueOnce(thread());
    const recovered = deferred<ThreadState>();
    getThreadMock.mockReturnValueOnce(recovered.promise);
    fetchMock.mockResolvedValue(streamResponse([sse("token", { text: "Draf" })], "drop"));
    const { result, statuses } = setup();
    await waitFor(() => expect(getThreadMock).toHaveBeenCalledTimes(1));

    let sent!: Promise<void>;
    act(() => {
      sent = result.current.send("Add three moons");
    });
    expect(result.current.status).toBe("streaming");
    await waitFor(() => expect(result.current.status).toBe("reconnecting"));
    await act(async () => {
      recovered.resolve(
        thread({
          messages: [
            { role: "user", content: "Add three moons" },
            { role: "assistant", content: "Drafted it." },
          ],
          pending_interrupt: pendingOf("p_1"),
          usage: usage(0.002),
        }),
      );
      await sent;
    });

    expect(statuses.indexOf("reconnecting")).toBeGreaterThan(statuses.indexOf("streaming"));
    expect(result.current.status).toBe("idle");
    expect(getThreadMock).toHaveBeenCalledTimes(2);
    expect(result.current.messages.at(-1)).toEqual({ role: "assistant", content: "Drafted it." });
    expect(result.current.pending?.proposals[0].proposal_id).toBe("p_1");
    expect(result.current.usage?.cost_usd).toBe(0.002);
  });

  it("also reconnects when the stream closes without done or error", async () => {
    getThreadMock.mockResolvedValueOnce(thread());
    const recovered = deferred<ThreadState>();
    getThreadMock.mockReturnValueOnce(recovered.promise);
    fetchMock.mockResolvedValue(streamResponse([sse("token", { text: "Hi" })], "close"));
    const { result } = setup();
    await waitFor(() => expect(getThreadMock).toHaveBeenCalledTimes(1));
    let sent!: Promise<void>;
    act(() => {
      sent = result.current.send("Hello");
    });
    await waitFor(() => expect(result.current.status).toBe("reconnecting"));
    await act(async () => {
      recovered.resolve(thread());
      await sent;
    });
    expect(getThreadMock).toHaveBeenCalledTimes(2);
    expect(result.current.status).toBe("idle");
  });

  it("streams tokens and tool calls, records turn events, and ends on done", async () => {
    getThreadMock.mockResolvedValue(thread());
    const invalidate = vi.spyOn(qc, "invalidateQueries");
    fetchMock.mockResolvedValue(
      streamResponse([
        sse("node", { name: "agent", phase: "start" }),
        sse("llm_request", { call: 1 }) + sse("token", { text: "Let me " }),
        sse("token", { text: "look." }),
        sse("tool_call", { name: "search_canon", args: { query: "moons" } }),
        sse("tool_result", { name: "search_canon", summary: "4 hits" }),
        sse("llm_response", { call: 1 }) + sse("node", { name: "agent", phase: "end", ms: 800 }),
        sse("token", { text: "Velmar has one moon." }),
        sse("usage", { turn: usage(0.001), total: usage(0.004) }),
        sse("done", {}),
      ]),
    );
    const { result } = setup();
    await waitFor(() => expect(getThreadMock).toHaveBeenCalledTimes(1));
    await act(async () => {
      await result.current.send("How many moons?");
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/proxy/threads/t1/messages",
      expect.objectContaining({ method: "POST" }),
    );
    expect(bodyOf(fetchMock.mock.calls[0])).toEqual({ content: "How many moons?" });
    expect(result.current.messages).toEqual([
      { role: "user", content: "How many moons?" },
      {
        role: "assistant",
        content: "Let me look.",
        tool_calls: [{ id: null, name: "search_canon", args: { query: "moons" } }],
      },
      { role: "tool", name: "search_canon", content: "" },
      { role: "assistant", content: "Velmar has one moon." },
    ]);
    expect(result.current.status).toBe("idle");
    expect(result.current.streaming).toBe(false);
    expect(result.current.usage?.cost_usd).toBe(0.004);
    expect(getThreadMock).toHaveBeenCalledTimes(1); // no reconnect after done
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["thread", "t1"] });
    expect(result.current.turnEvents).toHaveLength(1);
    expect(result.current.turnEvents[0].kind).toBe("message");
    expect(result.current.turnEvents[0].events.map((e) => e.event)).toEqual([
      "node", "llm_request", "tool_call", "tool_result", "llm_response", "node", "usage",
    ]);
    expect(localStorage.getItem(TOUR_KEYS.chatted)).toBe("1");
  });

  it("treats error as terminal: no reconnect, status error, message kept", async () => {
    getThreadMock.mockResolvedValue(thread());
    const invalidate = vi.spyOn(qc, "invalidateQueries");
    fetchMock.mockResolvedValue(
      streamResponse([
        sse("token", { text: "Hm" }),
        sse("error", { message: "The model service is unavailable right now. Please try again.", retryable: true }),
      ]),
    );
    const { result, statuses } = setup();
    await waitFor(() => expect(getThreadMock).toHaveBeenCalledTimes(1));
    await act(async () => {
      await result.current.send("Hello");
    });
    expect(statuses).not.toContain("reconnecting");
    expect(result.current.status).toBe("error");
    expect(result.current.error).toMatch(/model service is unavailable/);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["thread", "t1"] });
  });

  it("shows the pending-approval message on a 409 approval pending and restores the card", async () => {
    getThreadMock.mockResolvedValueOnce(thread());
    getThreadMock.mockResolvedValueOnce(thread({ pending_interrupt: pendingOf("p_1") }));
    fetchMock.mockResolvedValue(errorResponse(409, "approval pending"));
    const { result } = setup();
    await waitFor(() => expect(getThreadMock).toHaveBeenCalledTimes(1));
    await act(async () => {
      await result.current.send("Another idea");
    });
    expect(result.current.error).toBe("Decide on the pending change first");
    expect(result.current.pending?.proposals).toHaveLength(1);
  });

  it("collects one decision per proposal and submits them together, in pending order", async () => {
    getThreadMock.mockResolvedValueOnce(thread({ pending_interrupt: pendingOf("p_a", "p_b") }));
    // After the decision turn the thread is re-read (review notes are not streamed).
    getThreadMock.mockResolvedValueOnce(thread({ pending_interrupt: pendingOf("p_a") }));
    fetchMock.mockResolvedValue(
      streamResponse([sse("interrupt", pendingOf("p_a")), sse("done", {})]),
    );
    const { result } = setup();
    await waitFor(() => expect(result.current.pending?.proposals).toHaveLength(2));

    await act(async () => {
      await result.current.choose({ proposal_id: "p_b", action: "reject" });
    });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(result.current.chosen).toEqual({ p_b: { proposal_id: "p_b", action: "reject" } });

    await act(async () => {
      await result.current.choose({ proposal_id: "p_a", action: "approve" });
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/proxy/threads/t1/decisions");
    expect(bodyOf(fetchMock.mock.calls[0])).toEqual({
      decisions: [
        { proposal_id: "p_a", action: "approve" },
        { proposal_id: "p_b", action: "reject" },
      ],
    });
    // The re-check asks again about p_a: the old choice must not carry over.
    expect(result.current.pending?.proposals.map((p) => p.proposal_id)).toEqual(["p_a"]);
    expect(result.current.chosen).toEqual({});
  });

  it("submits at once when there is a single proposal, and marks the myth step", async () => {
    getThreadMock.mockResolvedValueOnce(thread({ pending_interrupt: pendingOf("p_1") }));
    getThreadMock.mockResolvedValueOnce(
      thread({ messages: [{ role: "review", name: "review", content: "Review: p_1 committed." }] }),
    );
    fetchMock.mockResolvedValue(streamResponse([sse("done", {})]));
    const { result } = setup();
    await waitFor(() => expect(result.current.pending).not.toBeNull());
    await act(async () => {
      await result.current.choose({ proposal_id: "p_1", action: "save_as_myth" });
    });
    expect(bodyOf(fetchMock.mock.calls[0])).toEqual({
      decisions: [{ proposal_id: "p_1", action: "save_as_myth" }],
    });
    expect(result.current.pending).toBeNull();
    expect(result.current.messages.at(-1)?.role).toBe("review");
    expect(localStorage.getItem(TOUR_KEYS.myth)).toBe("1");
  });

  it("refuses to send decisions that do not name exactly the pending ids", async () => {
    getThreadMock.mockResolvedValue(thread({ pending_interrupt: pendingOf("p_a", "p_b") }));
    const { result } = setup();
    await waitFor(() => expect(result.current.pending).not.toBeNull());
    await act(async () => {
      await result.current.decide([{ proposal_id: "p_a", action: "approve" }]);
    });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(result.current.error).toMatch(/every pending change/i);
  });

  it("marks the conflict step when an interrupt carries a conflict flag", async () => {
    getThreadMock.mockResolvedValue(thread());
    const withConflict = pendingOf("p_1");
    withConflict.checks.p_1 = {
      ...withConflict.checks.p_1,
      verdict: "conflict",
      flags: [
        {
          kind: "conflict", entry_id: "ent_0012", title: "Ister", fact_key: "Moons",
          existing_fact: "One", new_fact: "Three", existing_quote: null, new_quote: null,
          severity: "hard", explanation: "", suggested_fix: null, existing_secret: false,
        },
      ],
    };
    fetchMock.mockResolvedValue(streamResponse([sse("interrupt", withConflict), sse("done", {})]));
    const { result } = setup();
    await waitFor(() => expect(getThreadMock).toHaveBeenCalledTimes(1));
    await act(async () => {
      await result.current.send("Velmar has three moons");
    });
    expect(result.current.pending?.checks.p_1.verdict).toBe("conflict");
    expect(localStorage.getItem(TOUR_KEYS.conflict)).toBe("1");
  });
});
