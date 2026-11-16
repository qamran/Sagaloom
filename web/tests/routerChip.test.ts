import { describe, expect, it } from "vitest";
import { routerChipLabel } from "@/lib/routerChip";

describe("routerChipLabel", () => {
  it("is the mode alone for an LLM decision", () => {
    expect(routerChipLabel("query")).toBe("Router · query");
    expect(routerChipLabel("query", "llm", null)).toBe("Router · query");
  });

  it("adds Jev and its rounded confidence for a Jev decision", () => {
    expect(routerChipLabel("edit", "jev", 0.966)).toBe("Router · edit · Jev 97%");
  });

  it("drops the suffix when a Jev decision has no confidence", () => {
    expect(routerChipLabel("edit", "jev", null)).toBe("Router · edit");
  });
});
