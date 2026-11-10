import { describe, expect, it } from "vitest";
import { entryIsNc, licenceText } from "@/lib/sources";

describe("entryIsNc", () => {
  it("is true when any source is non-commercial", () => {
    expect(entryIsNc({ sources: [{ nc: false }, { nc: true }] })).toBe(true);
  });
  it("is false with no sources, none NC, or a missing list", () => {
    expect(entryIsNc({ sources: [] })).toBe(false);
    expect(entryIsNc({ sources: [{ nc: false }] })).toBe(false);
    expect(entryIsNc({})).toBe(false);
    expect(entryIsNc(null)).toBe(false);
  });
});

describe("licenceText", () => {
  it("gives the licence as reported", () => {
    expect(licenceText({ licence: "Creative Commons Attribution-Share Alike 4.0" })).toBe(
      "Creative Commons Attribution-Share Alike 4.0",
    );
  });
  it("says licence not reported for null, empty or missing", () => {
    expect(licenceText({ licence: null })).toBe("licence not reported");
    expect(licenceText({ licence: "" })).toBe("licence not reported");
    expect(licenceText({})).toBe("licence not reported");
  });
});
