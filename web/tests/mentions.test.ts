import { describe, expect, it } from "vitest";
import { linkEntities, matcherBuildCount, suggestEntries, type Named } from "@/lib/mentions";

const e = (id: string, title: string, type: Named["type"], aliases: string[] = [], status: Named["status"] = "canon"): Named => ({
  id, title, type, aliases, status,
});
const entries = [
  e("ent_0001", "Velmar", "place"),
  e("ent_0002", "The City of Velmar", "place", ["the Ash City"]),
  e("ent_0012", "Ister", "place", ["the red moon"]),
  e("ent_0019", "The Choir Ledger", "item", [], "secret"),
];
const chips = (p: ReturnType<typeof linkEntities>) => p.filter((x) => typeof x !== "string");

describe("linkEntities", () => {
  it("links an id, a title and an alias, keeping the matched text", () => {
    const p = linkEntities("Ister, the red moon (ent_0012) over velmar", entries, false);
    expect(p).toEqual([
      { entry: entries[2], text: "Ister" },
      ", ",
      { entry: entries[2], text: "the red moon" },
      " (",
      { entry: entries[2], text: "ent_0012" },
      ") over ",
      { entry: entries[0], text: "velmar" },
    ]);
  });
  it("reuses its matcher for the same entries", () => {
    const own = [e("ent_0100", "Quillon", "place")];
    const before = matcherBuildCount();
    linkEntities("Quillon", own, false);
    linkEntities("in Quillon again", own, false);
    expect(matcherBuildCount() - before).toBe(1);
    linkEntities("Quillon", own, true);
    expect(matcherBuildCount() - before).toBe(2);
    linkEntities("Quillon", [...own], false);
    expect(matcherBuildCount() - before).toBe(3);
  });
  it("a 3-letter alias chips only as written", () => {
    const ash = [e("ent_0200", "Ashwin", "character", ["Ash"])];
    expect(chips(linkEntities("Ash sat by the ash tree.", ash, false))).toEqual([{ entry: ash[0], text: "Ash" }]);
    expect(chips(linkEntities("ASH and ash", ash, false))).toEqual([]);
  });
  it("a 4-letter alias chips in any case", () => {
    const vale = [e("ent_0201", "Valerian", "character", ["Vale"])];
    expect(chips(linkEntities("Down in the vale.", vale, false))).toEqual([{ entry: vale[0], text: "vale" }]);
  });
  it("prefers the longest match", () => {
    const p = linkEntities("In the city of Velmar.", entries, false);
    expect(chips(p)).toEqual([{ entry: entries[1], text: "the city of Velmar" }]);
  });
  it("does not match inside a word", () => {
    expect(linkEntities("Velmarish folk", entries, false)).toEqual(["Velmarish folk"]);
  });
  it("keeps a secret entry as text while hidden and links it when shown", () => {
    expect(linkEntities("See ent_0019 and the Choir Ledger", entries, false)).toEqual(["See ent_0019 and the Choir Ledger"]);
    expect(chips(linkEntities("See ent_0019 and the Choir Ledger", entries, true))).toHaveLength(2);
  });
  it("leaves an unknown id as text", () => {
    expect(linkEntities("ent_9999", entries, false)).toEqual(["ent_9999"]);
  });
});

describe("suggestEntries", () => {
  const many = Array.from({ length: 12 }, (_, i) => e(`ent_${100 + i}`, `Moon ${i}`, "place"));
  it("ranks prefix matches before substring matches", () => {
    const list = [e("ent_0001", "Red Ister", "place"), e("ent_0002", "Istermoor", "place")];
    expect(suggestEntries("ister", list, false).map((x) => x.id)).toEqual(["ent_0002", "ent_0001"]);
  });
  it("matches aliases", () => {
    expect(suggestEntries("red m", entries, false).map((x) => x.id)).toEqual(["ent_0012"]);
  });
  it("excludes secrets while hidden", () => {
    expect(suggestEntries("choir", entries, false)).toEqual([]);
    expect(suggestEntries("choir", entries, true)).toHaveLength(1);
  });
  it("limits to 8", () => {
    expect(suggestEntries("moon", many, false)).toHaveLength(8);
  });
});
