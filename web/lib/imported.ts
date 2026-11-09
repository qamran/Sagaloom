const HEADING = /^## Imported from (.+ \(\d{4}-\d{2}-\d{2}\))\s*$/gm;

/** Whether a `## ` heading text (without the `## `) is a dated `Imported from …` heading. */
export function isImportedHeading(heading: string): boolean {
  return /^Imported from .+ \(\d{4}-\d{2}-\d{2}\)\s*$/.test(heading);
}

/** The `<label> (<date>)` part of each `## Imported from …` heading in an entry body, in order. */
export function importedSections(body: string): string[] {
  return Array.from(body.matchAll(HEADING), (m) => m[1]);
}
