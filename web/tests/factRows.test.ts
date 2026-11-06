import { describe, expect, it } from "vitest";
import { buildFactRows, lineDiff } from "@/lib/factRows";
import type { CheckResult, Entry, Fact, Flag, Proposal } from "@/lib/types";

const fact = (key: string, value: string, status: Fact["status"] = "canon"): Fact => ({
  key, value, refs: [], status, told_by: null,
});

const council = {
  id: "ent_0002", world_id: "w1", title: "Harbour Council", type: "faction",
  body: "Seven seats govern Velmar's harbour.", status: "canon", source: "user", source_url: null,
  licence: null, trusted: true, aliases: [], links: [], version: 2, created_at: "", updated_at: "",
  facts: [fact("Seats", "Seven"), fact("Meets at", "The Tidehall"), fact("Chaired by", "Mayor Elsbeth Varr")],
} as Entry;

const draftOf = (e: Entry, facts: Fact[]) => ({
  title: e.title, type: e.type, body: e.body, status: e.status, aliases: e.aliases, facts,
});

const update = (facts: Fact[]): Proposal => ({
  proposal_id: "p_1", action: "update", world_id: "w1", entry_id: council.id, before: council,
  after: draftOf(council, facts),
});

const flag = (over: Partial<Flag>): Flag => ({
  kind: "conflict", entry_id: "ent_0011", title: "The Salt Guild", fact_key: null, existing_fact: null,
  new_fact: null, existing_quote: null, new_quote: null, severity: null, explanation: "",
  suggested_fix: null, existing_secret: false, ...over,
});

const retcon = flag({
  kind: "retcon", entry_id: "ent_0002", title: "Harbour Council", fact_key: "Seats",
  existing_fact: "Seven", new_fact: "Five", explanation: "Changes established canon: Seven → Five",
});
const hard = flag({
  kind: "conflict", fact_key: "seats", existing_fact: "Two of seven", new_fact: "Five", severity: "hard",
  explanation: "The Salt Guild holds two of seven seats.",
});

const check = (flags: Flag[]): CheckResult => ({ proposal_id: "p_1", verdict: "none", flags, dependents: [] });

const fiveSeats = [fact("Seats", "Five"), fact("Meets at", "The Tidehall"), fact("Chaired by", "Mayor Elsbeth Varr")];

describe("buildFactRows", () => {
  it("gives one row per stored key, in stored order, with conflict over retcon", () => {
    const rows = buildFactRows(update(fiveSeats), check([retcon, hard]));
    expect(rows.map((r) => [r.key, r.result])).toEqual([
      ["Seats", "Conflict"],
      ["Meets at", "Matches"],
      ["Chaired by", "Matches"],
    ]);
    expect(rows[0].flags).toEqual([retcon, hard]);
    expect(rows[0].canon).toEqual([fact("Seats", "Seven")]);
    expect(rows[0].proposed).toEqual([fact("Seats", "Five")]);
    expect(rows[1].flags).toEqual([]);
  });

  it("marks a retcon-only key as Changed (retcon)", () => {
    const rows = buildFactRows(update(fiveSeats), check([retcon]));
    expect(rows[0].result).toBe("Changed (retcon)");
  });

  it("marks a possible conflict, a note, a new key, a dropped key and a changed myth", () => {
    const possible = { ...hard, severity: "possible" as const };
    expect(buildFactRows(update(fiveSeats), check([possible]))[0].result).toBe("Possible conflict");
    const note = flag({ kind: "note", severity: "note", fact_key: "Seats", explanation: "Worth a look." });
    expect(buildFactRows(update(fiveSeats), check([note]))[0].result).toBe("Note");

    const added = buildFactRows(update([...council.facts, fact("Motto", "Salt and tide")]), check([]));
    expect(added.map((r) => [r.key, r.result])).toEqual([
      ["Seats", "Matches"], ["Meets at", "Matches"], ["Chaired by", "Matches"], ["Motto", "New"],
    ]);
    expect(added[3].canon).toEqual([]);

    const dropped = buildFactRows(update(council.facts.slice(0, 2)), check([]));
    expect(dropped[2]).toMatchObject({ key: "Chaired by", result: "Removed", proposed: [] });

    const myth = { ...council, facts: [fact("Founded by", "A drowned king", "myth")] } as Entry;
    const changed = buildFactRows(
      { ...update([]), before: myth, after: draftOf(myth, [fact("Founded by", "A sea witch", "myth")]) },
      check([]),
    );
    expect(changed).toMatchObject([{ key: "Founded by", result: "Changed", flags: [] }]);
  });

  it("marks a same value whose status or teller changed as Changed", () => {
    const mythic = buildFactRows(update([fact("Seats", "Seven", "myth"), ...council.facts.slice(1)]), check([]));
    expect(mythic[0].result).toBe("Changed");
    const told = { ...fact("Seats", "Seven"), told_by: "The Salt Guild" };
    expect(buildFactRows(update([told, ...council.facts.slice(1)]), check([]))[0].result).toBe("Changed");
  });

  it("matches keys and values after normalising case and spacing", () => {
    const rows = buildFactRows(update([fact("  seats ", "seven"), ...council.facts.slice(1)]), check([]));
    expect(rows.map((r) => r.result)).toEqual(["Matches", "Matches", "Matches"]);
  });

  it("adds a row for a flag whose key names no fact on either side", () => {
    const other = flag({ kind: "conflict", severity: "hard", fact_key: "Harbour master", existing_fact: "Old Bren" });
    const rows = buildFactRows(update(council.facts), check([other]));
    expect(rows.at(-1)).toMatchObject({ key: "Harbour master", canon: [], proposed: [], result: "Conflict", flags: [other] });
  });

  it("gives a create one row per keyed flag", () => {
    const create: Proposal = {
      proposal_id: "p_1", action: "create", world_id: "w1", entry_id: null, before: null,
      after: draftOf(council, [fact("Seats", "Five")]),
    };
    const rows = buildFactRows(create, check([hard, flag({ kind: "note", explanation: "Prose only." })]));
    expect(rows).toEqual([
      {
        key: "seats", canon: [], proposed: [fact("Seats", "Five")], result: "Conflict", flags: [hard],
      },
    ]);
  });

  it("gives a delete no rows", () => {
    const del: Proposal = { ...update([]), action: "delete", after: null };
    expect(buildFactRows(del, check([]))).toEqual([]);
  });
});

describe("lineDiff", () => {
  it("reports only the fields that changed", () => {
    expect(lineDiff(council, { ...draftOf(council, council.facts), status: "secret" })).toEqual([
      { field: "status", old: "canon", new: "secret" },
    ]);
  });

  it("reports changed aliases joined with commas", () => {
    expect(lineDiff(council, { ...draftOf(council, council.facts), aliases: ["the Seven", "the Board"] })).toEqual([
      { field: "aliases", old: "", new: "the Seven, the Board" },
    ]);
  });
});
