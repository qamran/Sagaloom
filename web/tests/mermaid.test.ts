import { describe, expect, it } from "vitest";
import { highlightMermaid } from "@/lib/mermaid";

// Shaped like draw_mermaid(): nodes are declared as `id(label)`, edges follow.
const DARK =
  "\n\tclassDef default fill:#1d2321,stroke:#4a5550,color:#e6e3da;\n\tclassDef last fill:#2a2547,stroke:#8f84f0,color:#e6e3da;";
const SRC = "graph TD;\n\t__start__([__start__]):::first\n\tguard(guard)\n\trouter(router)\n\t__start__ --> guard;\n\tguard --> router;\n";

describe("highlightMermaid", () => {
  it("appends the classDef and class lines", () => {
    expect(highlightMermaid(SRC, ["guard", "router"])).toBe(
      `${SRC}${DARK}\n\tclassDef lastrun fill:#3a2f1a,stroke:#d9a441,stroke-width:2px;\n\tclass guard,router lastrun;`,
    );
  });
  it("ignores names that are not in the source", () => {
    expect(highlightMermaid(SRC, ["guard", "ghost"])).toContain("class guard lastrun;");
    expect(highlightMermaid(SRC, ["ghost"])).toBe(`${SRC}${DARK}`);
  });
  it("still restyles for the dark theme when no node is highlighted", () => {
    expect(highlightMermaid(SRC, [])).toBe(`${SRC}${DARK}`);
  });
  it("matches whole node ids only", () => {
    const src = "graph TD;\n\tagent_x(agent_x)\n\tagent_x --> agent_x;\n";
    expect(highlightMermaid(src, ["agent"])).toBe(`${src}${DARK}`);
  });
  it("ignores names with punctuation", () => {
    const src = "graph TD;\n\tagent(agent)\n\tabnt(abnt)\n";
    expect(highlightMermaid(src, ["a.nt", "agent;", "ag ent"])).toBe(`${src}${DARK}`);
  });
});
