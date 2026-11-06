const HEADING = /^## Imported from (.+ \(\d{4}-\d{2}-\d{2}\))\s*$/gm;

/** The `<label> (<date>)` part of each `## Imported from …` heading in an entry body, in order. */
export function importedSections(body: string): string[] {
  return Array.from(body.matchAll(HEADING), (m) => m[1]);
}
