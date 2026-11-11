import { describe, expect, it } from "vitest";
import { stepOf, stepsFromRoles } from "@/lib/steps";
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
});
