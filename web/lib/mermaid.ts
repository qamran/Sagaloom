/** Marks the nodes of the last run in Mermaid source. Names the graph does not have are ignored. */
export function highlightMermaid(src: string, nodes: string[]): string {
  const known = nodes.filter((n) => new RegExp(`(^|[^\w])${n.replace(/\W/g, "\$&")}([^\w]|$)`).test(src));
  if (known.length === 0) return src;
  return `${src}\n\tclassDef lastrun fill:#3a2f1a,stroke:#d9a441,stroke-width:2px;\n\tclass ${known.join(",")} lastrun;`;
}
