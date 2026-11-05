import { describe, expect, it } from "vitest";
import { highlightMermaid } from "@/lib/mermaid";

// Shaped like draw_mermaid(): nodes are declared as `id(label)`, edges follow.
const SRC = "graph TD;\n\t__start__([__start__]):::first\n\tguard(guard)\n\trouter(router)\n\t__start__ --> guard;\n\tguard --> router;\n";

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
  it("matches whole node ids only", () => {
    const src = "graph TD;\n\tagent_x(agent_x)\n\tagent_x --> agent_x;\n";
    expect(highlightMermaid(src, ["agent"])).toBe(src);
  });
  it("ignores names with punctuation", () => {
    const src = "graph TD;\n\tagent(agent)\n\tabnt(abnt)\n";
    expect(highlightMermaid(src, ["a.nt", "agent;", "ag ent"])).toBe(src);
  });
});
