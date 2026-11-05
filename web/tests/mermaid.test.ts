import { describe, expect, it } from "vitest";
import { highlightMermaid } from "@/lib/mermaid";

const SRC = "graph TD;\n\t__start__ --> guard;\n\tguard --> router;\n";

describe("highlightMermaid", () => {
  it("appends the classDef and class lines", () => {
    expect(highlightMermaid(SRC, ["guard", "router"])).toBe(
      `${SRC}\n\tclassDef lastrun fill:#3a2f1a,stroke:#d9a441,stroke-width:2px;\n\tclass guard,router lastrun;`,
    );
  });
  it("ignores names that are not in the source", () => {
    expect(highlightMermaid(SRC, ["guard", "ghost"])).toContain("class guard lastrun;");
    expect(highlightMermaid(SRC, ["ghost"])).toBe(SRC);
  });
  it("leaves the source unchanged for no nodes", () => {
    expect(highlightMermaid(SRC, [])).toBe(SRC);
  });
});
