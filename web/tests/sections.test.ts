import { describe, expect, it } from "vitest";
import { sectionsOf } from "@/lib/sections";

describe("sectionsOf", () => {
  it("gives one Description card when there are no headings", () => {
    expect(sectionsOf("A river city.")).toEqual([{ heading: "Description", text: "A river city.", imported: false }]);
  });
  it("gives an empty Description for an empty body", () => {
    expect(sectionsOf("")).toEqual([{ heading: "Description", text: "", imported: false }]);
  });
  it("treats text before the first ## as Description", () => {
    const s = sectionsOf("Intro.\n\n## History\nOld.");
    expect(s).toEqual([
      { heading: "Description", text: "Intro.", imported: false },
      { heading: "History", text: "Old.", imported: false },
    ]);
  });
  it("marks Imported from headings as imported", () => {
    const s = sectionsOf("Intro.\n\n## Imported from notes.md (2026-11-07)\nText.");
    expect(s[1]).toEqual({ heading: "Imported from notes.md (2026-11-07)", text: "Text.", imported: true });
  });
  it("does not mark an undated Imported from heading as imported", () => {
    expect(sectionsOf("Intro.\n## Imported from X\nT.")[1].imported).toBe(false);
  });
  it("a double-space imported heading counts in both", () => {
    expect(sectionsOf("Intro.\n##  Imported from x (2026-01-01)\nText.")[1]).toEqual({
      heading: "Imported from x (2026-01-01)",
      text: "Text.",
      imported: true,
    });
  });
  it("drops the empty Description when the body opens with a heading", () => {
    expect(sectionsOf("## History\nOld.")).toEqual([{ heading: "History", text: "Old.", imported: false }]);
  });
  it("trims a tab after the opener", () => {
    expect(sectionsOf("## \tHistory\nOld.")).toEqual([{ heading: "History", text: "Old.", imported: false }]);
  });
  it("does not split on ###", () => {
    const s = sectionsOf("Intro.\n### Sub\nMore.");
    expect(s).toHaveLength(1);
    expect(s[0].text).toBe("Intro.\n### Sub\nMore.");
  });
});
