import { describe, expect, it } from "vitest";
import { entryIsNc, isHttpsUrl, licenceText } from "@/lib/sources";

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
    expect(licenceText({ licence: null, licence_url: "" })).toBe("licence not reported");
  });
  it("gives the licence URL when the wiki reported only a URL (R-W3-2)", () => {
    const url = "https://creativecommons.org/licenses/by-sa/4.0/";
    expect(licenceText({ licence: null, licence_url: url })).toBe(url);
    expect(licenceText({ licence: "CC BY-SA 4.0", licence_url: url })).toBe("CC BY-SA 4.0");
  });
});

describe("isHttpsUrl", () => {
  it("is true only for an https URL", () => {
    expect(isHttpsUrl("https://en.wikipedia.org/wiki/Gandalf")).toBe(true);
    expect(isHttpsUrl("HTTPS://en.wikipedia.org/wiki/Gandalf")).toBe(true);
    expect(isHttpsUrl("http://en.wikipedia.org/wiki/Gandalf")).toBe(false);
    expect(isHttpsUrl("javascript:alert(1)")).toBe(false);
    expect(isHttpsUrl(null)).toBe(false);
  });
});
