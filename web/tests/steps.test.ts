import { describe, expect, it } from "vitest";
import { groupCalls, stepOf, stepsFromRoles } from "@/lib/steps";
import type { LlmCall } from "@/lib/turns";
import type { RoleUsage } from "@/lib/types";

const u = (role: string | null, calls = 1, p = 1, c = 1, cost = 0.001): RoleUsage => ({
  role, calls, prompt_tokens: p, completion_tokens: c, cost_usd: cost,
});

describe("steps", () => {
  it("stepOf maps every role", () => {
    expect(stepOf("judge")).toBe("check");
    expect(stepOf("agent")).toBe("chat");
    expect(stepOf("extractor")).toBe("extraction");
    expect(stepOf("guard")).toBe("guard");
    expect(stepOf("router")).toBe("router");
    expect(stepOf(null)).toBe("other");
    expect(stepOf("weird")).toBe("other");
  });

  it("stepsFromRoles orders by pipeline not input", () => {
    const out = stepsFromRoles([u("judge"), u("agent"), u("guard")]);
    expect(out.map((s) => s.name)).toEqual(["Guard", "Chat", "Check"]);
  });

  it("stepsFromRoles merges and sums", () => {
    const input = [u("weird", 2, 10, 5, 0.002), u(null, 1, 3, 2, 0.0005)];
    const out = stepsFromRoles(input);
    expect(out).toHaveLength(1);
    expect(out[0]).toMatchObject({ key: "other", name: "Other", calls: 3, prompt_tokens: 13, completion_tokens: 7 });
    expect(out.reduce((a, s) => a + s.cost_usd, 0)).toBeCloseTo(input.reduce((a, r) => a + r.cost_usd, 0), 10);
  });

  it("stepsFromRoles drops empty input", () => {
    expect(stepsFromRoles([])).toEqual([]);
  });

  it("stepOf sends names found on Object.prototype to other", () => {
    expect(stepOf("constructor")).toBe("other");
    expect(stepOf("toString")).toBe("other");
  });
});

const call = (role: string | null, cost: number | null, id = role ?? "none"): LlmCall => ({
  id, provider: "openrouter", model: "m", role, params: {}, messages: [], tools: [],
  response: cost === null ? null : { content: "", tool_calls: [], prompt_tokens: 10, completion_tokens: 5, cost_usd: cost, latency_ms: 1 },
});

describe("groupCalls", () => {
  it("keeps turn-wide indexes", () => {
    const groups = groupCalls([call("agent", 0.1, "a"), call("judge", 0.2), call("agent", 0.3, "b")]);
    expect(groups.map((g) => g.key)).toEqual(["chat", "check"]);
    expect(groups[0].items.map((i) => i.index)).toEqual([0, 2]);
    expect(groups[1].items.map((i) => i.index)).toEqual([1]);
    expect(groups[0]).toMatchObject({ name: "Chat", calls: 2, prompt_tokens: 20, completion_tokens: 10 });
    expect(groups[0].cost_usd).toBeCloseTo(0.4, 10);
  });

  it("counts a call without response as zero", () => {
    const [g] = groupCalls([call("agent", null)]);
    expect(g).toMatchObject({ calls: 1, prompt_tokens: 0, completion_tokens: 0, cost_usd: 0 });
  });

  it("keeps the cost of a role named like an Object.prototype member under Other", () => {
    const [g] = groupCalls([call("toString", 0.5)]);
    expect(g).toMatchObject({ key: "other", cost_usd: 0.5 });
  });
});
