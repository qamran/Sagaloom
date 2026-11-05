const ID = /^[A-Za-z0-9_]+$/;
const DECLARED = /^\s*([A-Za-z0-9_]+)[(\[{]/;

/** Marks the nodes of the last run in Mermaid source. Only names declared as nodes in the source count. */
export function highlightMermaid(src: string, nodes: string[]): string {
  const declared = new Set<string>();
  for (const line of src.split("\n")) {
    const m = DECLARED.exec(line);
    if (m) declared.add(m[1]);
  }
  const known = nodes.filter((n) => ID.test(n) && declared.has(n));
  if (known.length === 0) return src;
  return `${src}\n\tclassDef lastrun fill:#3a2f1a,stroke:#d9a441,stroke-width:2px;\n\tclass ${known.join(",")} lastrun;`;
}
