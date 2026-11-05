const ID = /^[A-Za-z0-9_]+$/;
const DECLARED = /^\s*([A-Za-z0-9_]+)[(\[{]/;

// draw_mermaid() fills nodes with light lavender (#f2f0ff), which leaves the dark theme's light labels
// unreadable. Later classDef lines override earlier ones, so these restyle the default and end nodes.
const DARK =
  "\n\tclassDef default fill:#1d2321,stroke:#4a5550,color:#e6e3da;\n\tclassDef last fill:#2a2547,stroke:#8f84f0,color:#e6e3da;";

/** Restyles the graph for the dark theme and marks the nodes of the last run. Only names declared as
 * nodes in the source count. */
export function highlightMermaid(src: string, nodes: string[]): string {
  const declared = new Set<string>();
  for (const line of src.split("\n")) {
    const m = DECLARED.exec(line);
    if (m) declared.add(m[1]);
  }
  const known = nodes.filter((n) => ID.test(n) && declared.has(n));
  if (known.length === 0) return `${src}${DARK}`;
  return `${src}${DARK}\n\tclassDef lastrun fill:#3a2f1a,stroke:#d9a441,stroke-width:2px;\n\tclass ${known.join(",")} lastrun;`;
}
