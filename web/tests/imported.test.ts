import { describe, expect, it } from "vitest";
import { importedSections } from "@/lib/imported";

describe("importedSections", () => {
  it("lists each imported heading's label and date in order", () => {
    const body = [
      "Original text.",
      "",
      "## Imported from notes.md (2026-11-05)",
      "First.",
      "",
      "## Imported from paste (2026-11-06)",
      "Second.",
    ].join("\n");
    expect(importedSections(body)).toEqual(["notes.md (2026-11-05)", "paste (2026-11-06)"]);
  });
  it("ignores other headings and inline mentions", () => {
    expect(importedSections("## History\nImported from nowhere\n### Imported from x (2026-01-01)")).toEqual([]);
  });
  it("is empty for an empty body", () => {
    expect(importedSections("")).toEqual([]);
  });
});
