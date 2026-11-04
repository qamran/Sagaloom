import { describe, expect, it } from "vitest";
import { buildTurnViews, viewFromEvents } from "@/lib/turns";
import type { PromptRecord } from "@/lib/types";

const rec = (id: string, run_id: string): PromptRecord => ({
  id, thread_id: "t", run_id, provider: "openrouter", model: "m", params: {},
  request: { messages: [{ role: "system", content: "s" }], tools: [] },
  response: null, started_at: "",
});

describe("turn views", () => {
  it("pairs llm_request with llm_response, nodes with timings and tools with results", () => {
    const v = viewFromEvents({
      turn: 1,
      kind: "message",
      events: [
        { event: "node", data: { name: "agent", phase: "start" } },
        { event: "llm_request", data: { id: "a", model: "m1", messages: [], tools: [] } },
        { event: "llm_response", data: { id: "a", content: "hi", tool_calls: [], prompt_tokens: 1, completion_tokens: 2, cost_usd: 0, latency_ms: 5 } },
        { event: "node", data: { name: "agent", phase: "end", ms: 800 } },
        { event: "tool_call", data: { name: "search_canon", args: { query: "x" } } },
        { event: "tool_result", data: { name: "search_canon", summary: "4 hits" } },
        { event: "node", data: { name: "approval_gate", phase: "start" } },
        { event: "interrupt", data: { proposals: [], checks: {} } },
      ],
    });
    expect(v.nodes).toEqual([
      { name: "agent", ms: 800, phase: "done" },
      { name: "approval_gate", ms: null, phase: "paused" },
    ]);
    expect(v.calls[0].response?.content).toBe("hi");
    expect(v.tools).toEqual([{ name: "search_canon", args: { query: "x" }, summary: "4 hits" }]);
  });

  it("keeps the role from a live llm_request event", () => {
    const v = viewFromEvents({
      turn: 1,
      kind: "message",
      events: [{ event: "llm_request", data: { id: "a", model: "m", role: "judge", messages: [], tools: [] } }],
    });
    expect(v.calls[0].role).toBe("judge");
  });

  it("groups the log by run id and does not list a live turn twice", () => {
    const live = [
      { turn: 1, kind: "message" as const, events: [{ event: "llm_request" as const, data: { id: "c", model: "m" } }] },
    ];
    const views = buildTurnViews(live, [rec("a", "r1"), rec("b", "r1"), rec("c", "r2")]);
    expect(views.map((v) => [v.label, v.calls.map((c) => c.id)])).toEqual([
      ["Turn 1", ["a", "b"]],
      ["Turn 2", ["c"]],
    ]);
  });
});
