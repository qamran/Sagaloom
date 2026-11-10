/** `Imported from <label> (<YYYY-MM-DD>)`: the one pattern source; group 1 is `<label> (<date>)`. */
const IMPORTED = String.raw`Imported from (.+ \(\d{4}-\d{2}-\d{2}\))`;
/** A `## ` heading line's opener (one or more spaces after `##`): the one source for `sections.ts` too. */
export const HEADING_OPENER = String.raw`^## +`;
const HEADING = new RegExp(String.raw`${HEADING_OPENER}${IMPORTED}\s*$`, "gm");
const HEADING_TEXT = new RegExp(String.raw`^${IMPORTED}\s*$`);

/** Whether a `## ` heading text (without the `## `) is a dated `Imported from …` heading. */
export function isImportedHeading(heading: string): boolean {
  return HEADING_TEXT.test(heading);
}

/** The `<label> (<date>)` part of each `## Imported from …` heading in an entry body, in order. */
export function importedSections(body: string): string[] {
  return Array.from(body.matchAll(HEADING), (m) => m[1]);
}
