import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { checkWikiUrls } from "@/lib/wikiUrls";

// One vector file serves the server (api/tests/wiki/test_pages.py) and this check, so the copy can't drift.
const vectors = JSON.parse(readFileSync(join(__dirname, "../../api/tests/fixtures/wiki_urls.json"), "utf-8")) as {
  accept: { in: string }[];
  reject: { in: string; error: string }[];
  lists: { in: string[]; error: string | null }[];
};

describe("checkWikiUrls", () => {
  it.each(vectors.accept)("accepts $in", ({ in: line }) => {
    expect(checkWikiUrls(line).error).toBeNull();
  });

  it.each(vectors.reject)("refuses $in with the server's copy", ({ in: line, error }) => {
    expect(checkWikiUrls(line).error).toBe(error);
  });

  it.each(vectors.lists.map((v, i) => ({ ...v, i })))("checks list vector $i", ({ in: lines, error }) => {
    expect(checkWikiUrls(lines.join("\n")).error).toBe(error);
  });

  it("returns the lines trimmed as typed, blanks dropped, for the server to normalise", () => {
    const text = "  https://en.wikipedia.org/wiki/Gandalf  \r\n\r\nhttps://en.wikipedia.org/wiki/Rivendell\n";
    expect(checkWikiUrls(text)).toEqual({
      urls: ["https://en.wikipedia.org/wiki/Gandalf", "https://en.wikipedia.org/wiki/Rivendell"],
      error: null,
    });
  });

  it("asks for 1 to 10 URLs when there are none", () => {
    expect(checkWikiUrls("  \n ").error).toBe("Paste 1 to 10 page URLs, one per line.");
  });
});
